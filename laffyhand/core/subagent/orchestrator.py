from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from laffyhand.core.event_bus import SessionEventBus
from laffyhand.core.models import (
    StepFinish,
    SubAgentEnd,
    SubAgentStart,
    TodoUpdate as TodoUpdateEvent,
)
from laffyhand.core.domain.messages import AssistantMessage
from laffyhand.core.models import CompactionConfig
from laffyhand.core.session.todo import TodoUpdate as TodoStatusUpdate
from laffyhand.core.subagent._shared import (
    build_subagent_state,
    map_event_to_subagent_delta,
)

if TYPE_CHECKING:
    from laffyhand.core.agent import AgentInfo
    from laffyhand.core.session.manager import SessionManager
    from laffyhand.core.session.todo import TodoManager
    from laffyhand.core.tools.registry import ToolRegistry
    from laffyhand.llm import LLM


MAX_SUBAGENT_DEPTH = 3


class _SubagentCtx:
    def __init__(self) -> None:
        self.subagent_id: str | None = None
        self.subagent_depth: int = 0


class SubagentOrchestrator:
    def __init__(
        self,
        session_manager: SessionManager,
        tool_registry: ToolRegistry,
        llm_provider: Callable[[str], LLM],
        compaction_config: CompactionConfig,
        todo_manager: TodoManager | None = None,
        *,
        event_bus: SessionEventBus,
    ) -> None:
        self.session_manager = session_manager
        self.tool_registry = tool_registry
        self._llm_provider = llm_provider
        self.compaction_config = compaction_config
        self.todo_manager = todo_manager
        self._event_bus = event_bus
        self._session_contexts: dict[str, _SubagentCtx] = {}

    def _get_context(self, session_id: str) -> _SubagentCtx:
        ctx = self._session_contexts.get(session_id)
        if ctx is None:
            ctx = _SubagentCtx()
            self._session_contexts[session_id] = ctx
        return ctx

    async def _publish(self, parent_session_id: str, event: Any) -> None:
        await self._event_bus.publish(parent_session_id, event)

    async def create_subagent(
        self,
        parent_session_id: str,
        agent_info: AgentInfo,
        prompt: str,
        description: str = "",
        todo_id: str | None = None,
    ) -> str:
        depth = self.session_manager.get_depth(parent_session_id)
        if depth > MAX_SUBAGENT_DEPTH:
            return (
                f"Error: maximum sub-agent depth ({MAX_SUBAGENT_DEPTH}) exceeded. "
                "Cannot spawn further sub-agents."
            )

        task_id = uuid.uuid4().hex[:12]
        ctx = self._get_context(parent_session_id)
        parent_subagent_id = ctx.subagent_id
        subagent_depth = (ctx.subagent_depth + 1) if ctx.subagent_id else 1

        if todo_id and self.todo_manager:
            self.todo_manager.update_task(
                todo_id,
                parent_session_id,
                TodoStatusUpdate(status="in_progress"),
            )
            await self._publish(parent_session_id, TodoUpdateEvent())

        prev_subagent_id = ctx.subagent_id
        prev_subagent_depth = ctx.subagent_depth
        ctx.subagent_id = task_id
        ctx.subagent_depth = subagent_depth

        try:
            result = await self._run_foreground(
                parent_session_id,
                agent_info,
                prompt,
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
                todo_id,
                parent_session_id,
                TodoStatusUpdate(status="completed"),
            )
            await self._publish(parent_session_id, TodoUpdateEvent())

        return result

    async def _run_foreground(
        self,
        parent_session_id: str,
        agent_info: AgentInfo,
        prompt: str,
        task_id: str = "",
        parent_subagent_id: str | None = None,
        subagent_depth: int = 0,
        description: str = "",
    ) -> str:
        child_state, child_registry = await build_subagent_state(
            self.session_manager,
            parent_session_id,
            agent_info,
            prompt,
            self.tool_registry.permission,
            self.tool_registry,
        )

        child_session_id = str(child_state.session_id)
        llm = self._llm_provider(parent_session_id)

        await self._publish(
            parent_session_id,
            SubAgentStart(
                id=task_id,
                parent_id=parent_subagent_id,
                agent_type=agent_info.name,
                description=description or prompt[:80],
                prompt=prompt,
                depth=subagent_depth,
            ),
        )

        from laffyhand.core.loop import AgentTurn

        turn = AgentTurn(
            child_state,
            llm,
            child_registry,
            compaction_config=CompactionConfig(
                tail_turns=self.compaction_config.tail_turns
            ),
            max_steps=agent_info.max_steps,
            session_manager=self.session_manager,
            event_bus=self._event_bus,
            session_id=child_session_id,
        )

        result_content = ""
        tool_call_count = 0

        async with self._event_bus.subscribe(child_session_id) as stream:
            task = asyncio.create_task(turn.run())
            try:
                async for event in stream:
                    tool_call_count += await map_event_to_subagent_delta(
                        task_id, event, self._event_bus, parent_session_id
                    )
                    if isinstance(event, StepFinish):
                        for msg in reversed(child_state.messages):
                            if isinstance(msg, AssistantMessage) and msg.content:
                                result_content = msg.content
                                break
            finally:
                await task

        assert child_state.session_id is not None
        self.session_manager.save_state(child_state.session_id, child_state)
        self.session_manager.complete(child_state.session_id)

        result = result_content.strip()
        if not result:
            result = "[No output]"

        step_usage = child_state.usage
        await self._publish(
            parent_session_id,
            SubAgentEnd(
                id=task_id,
                status="completed",
                summary=result[:200],
                tool_count=tool_call_count,
                input_tokens=step_usage.total_input,
                output_tokens=step_usage.total_output,
            ),
        )

        return f"<task>\n{result}\n</task>"
