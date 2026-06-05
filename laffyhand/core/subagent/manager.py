from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger

from laffyhand.core.llm.specs.models import AssistantMessage
from laffyhand.core.schemas import CompactionConfig
from laffyhand.core.events import SubAgentStart, SubAgentEnd
from laffyhand.core.subagent._shared import build_subagent_state, map_event_to_subagent_delta

if TYPE_CHECKING:
    from laffyhand.core.agent import AgentInfo
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
                        tool_call_count += await map_event_to_subagent_delta(task_id, event, _relay_event)

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
