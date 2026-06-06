from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from laffyhand.core.events import StepFinish, SubAgentEnd, SubAgentStart, TodoUpdate as TodoUpdateEvent
from laffyhand.core.llm.specs.models import AssistantMessage
from laffyhand.core.schemas import CompactionConfig
from laffyhand.core.session.todo import TodoStatus, TodoUpdate as TodoStatusUpdate
from laffyhand.core.subagent._shared import build_subagent_state, map_event_to_subagent_delta

if TYPE_CHECKING:
    from laffyhand.core.agent import AgentInfo
    from laffyhand.core.session.manager import SessionManager
    from laffyhand.core.session.todo import TodoManager
    from laffyhand.core.subagent.manager import SubagentManager
    from laffyhand.core.tools.registry import ToolRegistry
    from laffyhand.core.llm.facade import LLM


MAX_SUBAGENT_DEPTH = 3


@dataclass
class SessionContext:
    subagent_id: str | None = None
    subagent_depth: int = 0


class SubagentOrchestrator:
    def __init__(
        self,
        session_manager: SessionManager,
        tool_registry: ToolRegistry,
        subagent_manager: SubagentManager,
        llm_provider: Callable[[str], LLM],
        compaction_config: CompactionConfig,
        todo_manager: TodoManager | None = None,
        *,
        event_sink_provider: Callable[[str], Callable[[Any], Awaitable[None]] | None] | None = None,
    ) -> None:
        self.session_manager = session_manager
        self.tool_registry = tool_registry
        self.subagent_manager = subagent_manager
        self._llm_provider = llm_provider
        self.compaction_config = compaction_config
        self.todo_manager = todo_manager
        self._event_sink_provider = event_sink_provider
        self._session_contexts: dict[str, SessionContext] = {}

    def get_context(self, session_id: str) -> SessionContext:
        ctx = self._session_contexts.get(session_id)
        if ctx is None:
            ctx = SessionContext()
            self._session_contexts[session_id] = ctx
        return ctx

    async def create_subagent(
        self,
        parent_session_id: str,
        agent_info: AgentInfo,
        prompt: str,
        description: str = "",
        background: bool = False,
        todo_id: str | None = None,
        *,
        event_sink: Callable[[Any], Awaitable[None]] | None = None,
    ) -> str:
        depth = self.session_manager.get_depth(parent_session_id)
        if depth > MAX_SUBAGENT_DEPTH:
            return (
                f"Error: maximum sub-agent depth ({MAX_SUBAGENT_DEPTH}) exceeded. "
                "Cannot spawn further sub-agents."
            )

        task_id = uuid.uuid4().hex[:12]
        ctx = self.get_context(parent_session_id)
        parent_subagent_id = ctx.subagent_id
        subagent_depth = (ctx.subagent_depth + 1) if ctx.subagent_id else 1

        if todo_id and self.todo_manager:
            self.todo_manager.update_task(
                todo_id, parent_session_id, TodoStatusUpdate(status="in_progress"),
            )
            sink = event_sink or (self._event_sink_provider(parent_session_id) if self._event_sink_provider else None)
            if sink:
                await sink(TodoUpdateEvent())

        if background:
            bg_llm = self._llm_provider(parent_session_id)

            def _on_complete(_task_id: str, success: bool) -> None:
                if todo_id and self.todo_manager:
                    status: TodoStatus = "completed" if success else "pending"
                    self.todo_manager.update_task(
                        todo_id, parent_session_id, TodoStatusUpdate(status=status),
                    )
                    sink = event_sink or (self._event_sink_provider(parent_session_id) if self._event_sink_provider else None)
                    if sink:
                        asyncio.ensure_future(sink(TodoUpdateEvent()))

            await self.subagent_manager.spawn(
                parent_session_id=parent_session_id,
                agent_info=agent_info,
                prompt=prompt,
                llm=bg_llm,
                tool_registry=self.tool_registry,
                parent_permission=self.tool_registry.permission,
                session_manager=self.session_manager,
                compaction_config=self.compaction_config,
                on_complete=_on_complete,
                event_sink=event_sink or (self._event_sink_provider(parent_session_id) if self._event_sink_provider else None),
                task_id=task_id,
                parent_subagent_id=parent_subagent_id,
                subagent_depth=subagent_depth,
                description=description,
            )
            return f"Sub-agent [{agent_info.name}] started (id: {task_id[:8]}). I'll notify you when it completes."

        prev_subagent_id = ctx.subagent_id
        prev_subagent_depth = ctx.subagent_depth
        ctx.subagent_id = task_id
        ctx.subagent_depth = subagent_depth

        try:
            result = await self._run_foreground(
                parent_session_id, agent_info, prompt,
                event_sink=event_sink or (self._event_sink_provider(parent_session_id) if self._event_sink_provider else None),
                task_id=task_id,
                parent_subagent_id=parent_subagent_id,
                subagent_depth=subagent_depth,
                description=description,
            )
        finally:
            ctx.subagent_id = prev_subagent_id
            ctx.subagent_depth = prev_subagent_depth

        if todo_id and self.todo_manager:
            self.todo_manager.update_task(
                todo_id, parent_session_id, TodoStatusUpdate(status="completed"),
            )
            sink = event_sink or (self._event_sink_provider(parent_session_id) if self._event_sink_provider else None)
            if sink:
                await sink(TodoUpdateEvent())

        return result

    def cancel_session(self, session_id: str) -> None:
        self.subagent_manager.cancel_session(session_id)

    async def cancel_all(self) -> None:
        self.subagent_manager.cancel_all()

    async def _run_foreground(
        self,
        parent_session_id: str,
        agent_info: AgentInfo,
        prompt: str,
        event_sink: Callable[[Any], Awaitable[None]] | None = None,
        task_id: str = "",
        parent_subagent_id: str | None = None,
        subagent_depth: int = 0,
        description: str = "",
    ) -> str:
        child_state, child_registry = build_subagent_state(
            self.session_manager, parent_session_id, agent_info, prompt,
            self.tool_registry.permission, self.tool_registry,
        )

        llm = self._llm_provider(parent_session_id)

        if event_sink:
            await event_sink(
                SubAgentStart(
                    id=task_id, parent_id=parent_subagent_id,
                    agent_type=agent_info.name,
                    description=description or prompt[:80],
                    prompt=prompt, mode="foreground", depth=subagent_depth,
                )
            )

        result_content = ""
        tool_call_count = 0

        from laffyhand.core.loop import AgentTurn

        async for event in AgentTurn(
            child_state, llm, child_registry,
            compaction_config=CompactionConfig(tail_turns=self.compaction_config.tail_turns),
            max_steps=agent_info.max_steps,
            session_manager=self.session_manager,
        ).run():
            if event_sink:
                tool_call_count += await map_event_to_subagent_delta(task_id, event, event_sink)
            if isinstance(event, StepFinish):
                for msg in reversed(child_state.messages):
                    if isinstance(msg, AssistantMessage) and msg.content:
                        result_content = msg.content
                        break

        assert child_state.session_id is not None
        self.session_manager.save_state(child_state.session_id, child_state)
        self.session_manager.complete(child_state.session_id)

        result = result_content.strip()
        if not result:
            result = "[No output]"

        if event_sink:
            step_usage = child_state.usage
            await event_sink(
                SubAgentEnd(id=task_id, status="completed", summary=result[:200],
                            tool_count=tool_call_count,
                            input_tokens=step_usage.total_input,
                            output_tokens=step_usage.total_output)
            )

        return f"<task>\n{result}\n</task>"
