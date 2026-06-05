from __future__ import annotations

import asyncio
import os
import sys
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger

from laffyhand.core.llm.specs.models import AssistantMessage, SystemMessage, UserMessage
from laffyhand.core.schemas import (
    AgentState,
    CompactionConfig,
    SessionID,
    SessionUsage,
)
from laffyhand.core.schemas import (
    StepStart,
    TextStart,
    TextEnd,
    ReasoningStart,
    ReasoningEnd,
    Compacting,
    SubAgentStart,
    SubAgentDelta,
    SubAgentEnd,
    TextDelta,
    ReasoningDelta,
    ToolCall as StreamToolCall,
    ToolResult as StreamToolResult,
    ToolError as StreamToolError,
)
from laffyhand.core.tools.permission import SubagentPermissions

if TYPE_CHECKING:
    from laffyhand.core.agent.agent import AgentInfo
    from laffyhand.core.llm.facade import LLM
    from laffyhand.core.session.manager import SessionManager
    from laffyhand.core.tools.registry import ToolRegistry
    from laffyhand.core.tools.permission import PermissionManager


SubagentStatus = Literal["pending", "running", "completed", "error"]


@dataclass
class SubagentResult:
    task_id: str
    session_id: str
    parent_session_id: str
    agent_type: str
    status: SubagentStatus
    content: str = ""
    error: str = ""


@dataclass
class _RunningSubagent:
    task_id: str
    session_id: str
    parent_session_id: str
    agent_type: str
    task: asyncio.Task[None]
    status: SubagentStatus = "pending"


def build_subagent_state(
    session_manager: SessionManager,
    parent_session_id: str,
    agent_info: AgentInfo,
    prompt: str,
    parent_permission: PermissionManager,
    tool_registry: ToolRegistry,
) -> tuple[AgentState, ToolRegistry]:
    """Common sub-agent bootstrap — create child session, compose permissions, build AgentState.

    Returns (child_state, child_registry) for use by
    both foreground (_run_foreground) and background (spawn) paths.
    """
    child_session = session_manager.create_child(
        parent_id=parent_session_id,
        model=agent_info.model or "",
    )

    child_permission = SubagentPermissions.compose(
        parent_permission,
        agent_info.permission,
    )
    child_registry = SubagentPermissions.filter_registry(
        tool_registry,
        child_permission,
    )

    system_content = (
        agent_info.system_prompt or "You are a helpful sub-agent. Complete the assigned task."
    )

    now = datetime.now(timezone.utc)
    workspace = child_registry.workspace or os.getcwd()
    env_parts = [
        f"Working directory: {os.getcwd()}",
        f"Workspace: {workspace}",
        f"Platform: {sys.platform}",
        f"Current time: {now.isoformat()}",
    ]
    env_block = "<env>\n" + "\n".join(env_parts) + "\n</env>"

    system_prompt = f"<soul>\n{system_content.strip()}\n</soul>"
    system_prompt += f"\n{env_block}"
    system_prompt += f"\n{child_registry.build_tool_prompt()}"

    system_msg = SystemMessage(content=system_prompt)
    user_msg = UserMessage(content=prompt)

    child_state = AgentState(
        messages=[system_msg, user_msg],
        session_id=SessionID(child_session.id),
        usage=SessionUsage(context_size=0),
    )
    return child_state, child_registry


class SubagentManager:
    def __init__(
        self,
        max_concurrent: int = 2,
    ) -> None:
        self._running: dict[str, _RunningSubagent] = {}
        self._session_tasks: dict[str, set[str]] = {}
        self._pending_results: asyncio.Queue[SubagentResult] = asyncio.Queue()
        self._pending_events: dict[str, set[asyncio.Queue[Any]]] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def spawn(
        self,
        parent_session_id: str,
        agent_info: AgentInfo,
        prompt: str,
        llm: LLM,
        tool_registry: ToolRegistry,
        parent_permission: PermissionManager,
        session_manager: SessionManager,
        compaction_config: CompactionConfig | None = None,
        on_complete: Callable[[str, bool], None] | None = None,
        event_sink: Callable[[Any], Awaitable[None]] | None = None,
        task_id: str | None = None,
        parent_subagent_id: str | None = None,
        subagent_depth: int = 0,
        description: str = "",
    ) -> str:
        if task_id is None:
            task_id = uuid.uuid4().hex[:12]
        child_state, child_registry = build_subagent_state(
            session_manager,
            parent_session_id,
            agent_info,
            prompt,
            parent_permission,
            tool_registry,
        )

        # Create event queue for relaying background subagent events
        event_queue: asyncio.Queue[Any] | None = None
        if event_sink is not None:
            event_queue = asyncio.Queue()
            self._pending_events.setdefault(parent_session_id, set()).add(event_queue)

        async def _relay_event(evt: Any) -> None:
            if event_queue is not None:
                await event_queue.put(evt)

        async def _run() -> None:
            async with self._semaphore:
                running = self._running.get(task_id)
                if running is not None:
                    running.status = "running"

                success = False
                try:
                    await _relay_event(
                        SubAgentStart(
                            id=task_id,
                            parent_id=parent_subagent_id,
                            agent_type=agent_info.name,
                            description=description or prompt[:80],
                            prompt=prompt,
                            mode="background",
                            depth=subagent_depth,
                        )
                    )

                    from laffyhand.core.loop import agent_loop

                    tool_call_count = 0
                    async for event in agent_loop(
                        child_state,
                        llm,
                        child_registry,
                        compaction_config=compaction_config or CompactionConfig(),
                        max_steps=agent_info.max_steps,
                        session_manager=session_manager,
                    ):
                        if isinstance(event, TextDelta):
                            await _relay_event(
                                SubAgentDelta(
                                    id=task_id,
                                    kind="text",
                                    content=event.text,
                                )
                            )
                        elif isinstance(event, ReasoningDelta):
                            await _relay_event(
                                SubAgentDelta(
                                    id=task_id,
                                    kind="reasoning",
                                    content=event.text,
                                )
                            )
                        elif isinstance(event, StreamToolCall):
                            tool_call_count += 1
                            await _relay_event(
                                SubAgentDelta(
                                    id=task_id,
                                    kind="tool",
                                    tool_name=event.name,
                                    tool_input=event.input,
                                )
                            )
                        elif isinstance(event, StreamToolResult):
                            await _relay_event(
                                SubAgentDelta(
                                    id=task_id,
                                    kind="tool_result",
                                    tool_name=event.name,
                                    content=event.result,
                                )
                            )
                        elif isinstance(event, StreamToolError):
                            await _relay_event(
                                SubAgentDelta(
                                    id=task_id,
                                    kind="tool_result",
                                    tool_name=event.name,
                                    content=event.message,
                                )
                            )
                        elif isinstance(event, (StepStart, TextStart, TextEnd, ReasoningStart, ReasoningEnd, Compacting)):
                            await _relay_event(event)

                    assert child_state.session_id is not None
                    session_manager.save_state(child_state.session_id, child_state)
                    session_manager.complete(child_state.session_id)

                    last_content = ""
                    for msg in reversed(child_state.messages):
                        if isinstance(msg, AssistantMessage) and msg.content:
                            last_content = msg.content
                            break

                    assert child_state.session_id is not None
                    result = SubagentResult(
                        task_id=task_id,
                        session_id=child_state.session_id,
                        parent_session_id=parent_session_id,
                        agent_type=agent_info.name,
                        status="completed",
                        content=last_content,
                    )
                    success = True

                    step_usage = child_state.usage
                    await _relay_event(
                        SubAgentEnd(
                            id=task_id,
                            status="completed",
                            summary=last_content[:200],
                            tool_count=tool_call_count,
                            input_tokens=step_usage.total_input,
                            output_tokens=step_usage.total_output,
                        )
                    )
                except asyncio.CancelledError:
                    await _relay_event(
                        SubAgentEnd(
                            id=task_id,
                            status="cancelled",
                        )
                    )
                    assert child_state.session_id is not None
                    result = SubagentResult(
                        task_id=task_id,
                        session_id=child_state.session_id,
                        parent_session_id=parent_session_id,
                        agent_type=agent_info.name,
                        status="error",
                        error="Task cancelled",
                    )
                except Exception as e:
                    logger.exception(f"Subagent {task_id} failed: {e}")
                    assert child_state.session_id is not None
                    result = SubagentResult(
                        task_id=task_id,
                        session_id=child_state.session_id,
                        parent_session_id=parent_session_id,
                        agent_type=agent_info.name,
                        status="error",
                        error=str(e),
                    )
                    await _relay_event(
                        SubAgentEnd(
                            id=task_id,
                            status="error",
                            summary=str(e)[:200],
                        )
                    )

                await self._pending_results.put(result)

                if running is not None:
                    running.status = result.status

                if on_complete is not None:
                    on_complete(task_id, success)

                self._cleanup_task(task_id, parent_session_id)
                if event_queue is not None:
                    queues = self._pending_events.get(parent_session_id)
                    if queues:
                        queues.discard(event_queue)
                        if not queues:
                            self._pending_events.pop(parent_session_id, None)

        assert child_state.session_id is not None
        self._register_task(
            task_id, child_state.session_id, parent_session_id, agent_info.name, _run
        )
        return task_id

    def _register_task(
        self,
        task_id: str,
        session_id: str,
        parent_session_id: str,
        agent_type: str,
        coro: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        task: asyncio.Task[None] = asyncio.create_task(coro())
        running = _RunningSubagent(
            task_id=task_id,
            session_id=session_id,
            parent_session_id=parent_session_id,
            agent_type=agent_type,
            task=task,
            status="pending",
        )
        self._running[task_id] = running
        self._session_tasks.setdefault(parent_session_id, set()).add(task_id)

    def _cleanup_task(self, task_id: str, parent_session_id: str) -> None:
        self._running.pop(task_id, None)
        tasks = self._session_tasks.get(parent_session_id)
        if tasks:
            tasks.discard(task_id)
            if not tasks:
                self._session_tasks.pop(parent_session_id, None)

    async def poll_results(
        self,
        session_id: str,
        max_count: int = 5,
    ) -> list[SubagentResult]:
        results: list[SubagentResult] = []
        for _ in range(max_count):
            if self._pending_results.empty():
                break
            try:
                result = self._pending_results.get_nowait()
            except asyncio.QueueEmpty:
                break
            if result.parent_session_id == session_id:
                results.append(result)
            else:
                await self._pending_results.put(result)
        return results

    def cancel_session(self, session_id: str) -> None:
        tasks = self._session_tasks.get(session_id)
        if not tasks:
            return
        for task_id in list(tasks):
            running = self._running.get(task_id)
            if running is not None:
                running.task.cancel()
                logger.info(f"Cancelled subagent {task_id} for session {session_id}")
            self._cleanup_task(task_id, session_id)

    def cancel_all(self) -> None:
        """Cancel all running subagent tasks across all sessions."""
        for task_id in list(self._running):
            running = self._running.get(task_id)
            if running is not None:
                running.task.cancel()
                logger.info(f"Cancelled subagent {task_id} (cancel_all)")
            self._cleanup_task(task_id, running.parent_session_id if running else "")

    async def drain_events(self, session_id: str) -> list[Any]:
        """Drain buffered background subagent events for a parent session."""
        events: list[Any] = []
        queues = self._pending_events.get(session_id)
        if not queues:
            return events
        for queue in list(queues):
            while not queue.empty():
                try:
                    events.append(queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
        return events

    def active_count(self, session_id: str | None = None) -> int:
        if session_id is not None:
            tasks = self._session_tasks.get(session_id)
            return len(tasks) if tasks else 0
        return len(self._running)

    def list_active(self, session_id: str) -> list[dict[str, Any]]:
        tasks = self._session_tasks.get(session_id)
        if not tasks:
            return []
        result = []
        for task_id in tasks:
            running = self._running.get(task_id)
            if running is not None:
                result.append(
                    {
                        "task_id": task_id,
                        "agent_type": running.agent_type,
                        "status": running.status,
                    }
                )
        return result
