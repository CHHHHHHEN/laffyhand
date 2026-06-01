from __future__ import annotations

import asyncio
from collections.abc import Coroutine
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Literal

from loguru import logger

from laffyhand.agent.schemas import (
    AgentState, CompactionConfig, SessionUsage, SystemMessage, UserMessage,
)
from laffyhand.agent.tools.permission import SubagentPermissions

if TYPE_CHECKING:
    from laffyhand.agent.agent import AgentInfo
    from laffyhand.agent.llm.facade import LLM
    from laffyhand.agent.session.manager import SessionManager
    from laffyhand.agent.tools.registry import ToolRegistry
    from laffyhand.agent.tools.permission import PermissionManager


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
    system_content = (
        agent_info.prompt
        or "You are a helpful sub-agent. Complete the assigned task."
    )
    system_msg = SystemMessage(content=system_content)
    user_msg = UserMessage(content=prompt)

    child_permission = SubagentPermissions.compose(
        parent_permission,
        agent_info.permission,
    )
    child_registry = SubagentPermissions.filter_registry(
        tool_registry, child_permission,
    )

    child_state = AgentState(
        messages=[system_msg, user_msg],
        session_id=child_session.id,
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
    ) -> str:
        task_id = uuid.uuid4().hex[:12]
        child_state, child_registry = build_subagent_state(
            session_manager, parent_session_id, agent_info, prompt,
            parent_permission, tool_registry,
        )

        async def _run() -> None:
            async with self._semaphore:
                running = self._running.get(task_id)
                if running is not None:
                    running.status = "running"

                success = False
                try:
                    from laffyhand.agent.loop import agent_loop

                    async for event in agent_loop(
                        child_state,
                        llm,
                        child_registry,
                        compaction_config=compaction_config or CompactionConfig(),
                        max_steps=agent_info.max_steps,
                        session_manager=session_manager,
                    ):
                        pass

                    assert child_state.session_id is not None
                    session_manager.save_state(child_state.session_id, child_state)
                    session_manager.complete(child_state.session_id)

                    last_content = ""
                    if child_state.messages:
                        last = child_state.messages[-1]
                        if hasattr(last, "content") and last.content:
                            last_content = last.content

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

                await self._pending_results.put(result)

                if running is not None:
                    running.status = result.status

                if on_complete is not None:
                    on_complete(task_id, success)

                self._cleanup_task(task_id, parent_session_id)

        assert child_state.session_id is not None
        self._register_task(task_id, child_state.session_id, parent_session_id, agent_info.name, _run)
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
        self, session_id: str, max_count: int = 5,
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
                result.append({
                    "task_id": task_id,
                    "agent_type": running.agent_type,
                    "status": running.status,
                })
        return result



