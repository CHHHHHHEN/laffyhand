from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from laffyhand.core.event_bus import SessionEventBus
from laffyhand.core.loop.turn import AgentTurn
from laffyhand.core.models import CompactionConfig
from laffyhand.core.session.state_store import SessionStateStore

if TYPE_CHECKING:
    from laffyhand.llm import LLM
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
        event_bus: SessionEventBus,
    ) -> None:
        self._session_manager = session_manager
        self._tool_registry = tool_registry
        self._llm_provider = llm_provider
        self._compaction_config = compaction_config
        self._max_steps = max_steps
        self._title_scheduler = title_scheduler
        self._session_store = session_store
        self._event_bus = event_bus

    async def run_agent_turn(self, session_id: str):
        state = self._session_store.get(session_id)
        assert state is not None, f"state not found for session {session_id}"
        llm = self._llm_provider(session_id)

        session_obj = self._session_manager.get(session_id)
        agent_name = session_obj.agent_name if session_obj else ""

        turn = AgentTurn(
            state,
            llm,
            self._tool_registry,
            compaction_config=self._compaction_config,
            max_steps=self._max_steps,
            session_manager=self._session_manager,
            on_compacted=lambda child_sid: self._title_scheduler(
                child_sid, "on_compact"
            ),
            event_bus=self._event_bus,
            session_id=session_id,
            agent_name=agent_name,
        )

        async with self._event_bus.subscribe(session_id, is_primary=True) as stream:
            task = asyncio.create_task(turn.run())
            try:
                async for event in stream:
                    yield event
            finally:
                await task


__all__ = [
    "LoopOrchestrator",
]
