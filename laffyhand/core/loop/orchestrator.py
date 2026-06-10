from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from laffyhand.core.loop.turn import AgentTurn
from laffyhand.core.models import CompactionConfig
from laffyhand.core.session.state_store import SessionStateStore

if TYPE_CHECKING:
    from laffyhand.core.llm.facade import LLM
    from laffyhand.core.session import SessionManager
    from laffyhand.core.tools import ToolRegistry


class LoopOrchestrator:
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

__all__ = [
    "LoopOrchestrator",
]
