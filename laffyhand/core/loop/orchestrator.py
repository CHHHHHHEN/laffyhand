from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from laffyhand.core.loop.turn import AgentTurn
from laffyhand.core.models import CompactionConfig
from laffyhand.core.session.state_store import SessionStateStore

if TYPE_CHECKING:
    from laffyhand.core.llm.facade import LLM
    from laffyhand.core.session import SessionManager
    from laffyhand.core.tools import ToolRegistry


_TURN_DONE = object()


class LoopOrchestrator:
    """Manages agent turn lifecycle: foreground execution, background tasks, and cancellation."""

    def __init__(
        self,
        *,
        session_manager: SessionManager,
        tool_registry: ToolRegistry,
        llm_provider: Callable[[str], LLM],
        compaction_config: CompactionConfig,
        max_steps: int,
        title_scheduler: Callable[[str, str], None],
        session_store: SessionStateStore,
    ) -> None:
        self._session_manager = session_manager
        self._tool_registry = tool_registry
        self._llm_provider = llm_provider
        self._compaction_config = compaction_config
        self._max_steps = max_steps
        self._title_scheduler = title_scheduler
        self._session_store = session_store
        self._session_tasks: dict[str, asyncio.Task[None]] = {}
        self._session_event_queues: dict[str, asyncio.Queue[Any]] = {}

    async def run_agent_turn(
        self,
        session_id: str,
        event_sink: Callable[[Any], Awaitable[None]] | None = None,
    ):
        state = self._session_store.get(session_id)
        assert state is not None, f"state not found for session {session_id}"
        if event_sink is not None:
            self._session_store.set_event_sink(session_id, event_sink)
        llm = self._llm_provider(session_id)
        try:
            async for event in AgentTurn(
                state,
                llm,
                self._tool_registry,
                compaction_config=self._compaction_config,
                max_steps=self._max_steps,
                session_manager=self._session_manager,
                on_compacted=lambda child_sid: self._title_scheduler(
                    child_sid, "on_compact"
                ),
            ).run():
                yield event
        finally:
            self._session_store.pop_event_sink(session_id)

    def is_session_running(self, session_id: str) -> bool:
        return (
            session_id in self._session_tasks
            and not self._session_tasks[session_id].done()
        )

    async def start_background_agent_turn(
        self,
        session_id: str,
        event_sink: Callable[[Any], Awaitable[None]] | None = None,
    ) -> asyncio.Queue[Any]:
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._session_event_queues[session_id] = queue

        async def _run() -> None:
            try:
                async for event in self.run_agent_turn(
                    session_id=session_id,
                    event_sink=event_sink,
                ):
                    await queue.put(event)
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(f"Background agent turn failed for {session_id}")
            finally:
                await queue.put(_TURN_DONE)
                self._session_tasks.pop(session_id, None)
                self._session_event_queues.pop(session_id, None)
                self._session_store.pop_event_sink(session_id)

        task = asyncio.create_task(_run())
        self._session_tasks[session_id] = task
        return queue

    def cancel_background_agent_turn(self, session_id: str) -> None:
        task = self._session_tasks.get(session_id)
        if task is not None and not task.done():
            task.cancel()

    async def cancel_all(self) -> None:
        for sid in list(self._session_tasks):
            self.cancel_background_agent_turn(sid)
        if self._session_tasks:
            await asyncio.wait(list(self._session_tasks.values()), timeout=5.0)


__all__ = [
    "LoopOrchestrator",
]
