from __future__ import annotations

import asyncio
import copy
from typing import TYPE_CHECKING

from loguru import logger

from laffyhand.core.domain.messages import SystemMessage
from laffyhand.core.models import AgentState, SessionID

if TYPE_CHECKING:
    from laffyhand.core.session import SessionManager


class SessionStateStore:
    def __init__(self) -> None:
        self._states: dict[str, AgentState] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._pending_permissions: dict[
            str, tuple[asyncio.Event, str, str, bool | None, str | None]
        ] = {}


    # ── State access ──────────────────────────────────────────

    def get(self, session_id: str) -> AgentState | None:
        return self._states.get(session_id)

    def set(self, session_id: str, state: AgentState) -> None:
        self._states[session_id] = state

    def pop(self, session_id: str) -> AgentState | None:
        return self._states.pop(session_id, None)

    def items(self) -> list[tuple[str, AgentState]]:
        return list(self._states.items())

    # ── Lock management ───────────────────────────────────────

    def get_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

    # ── Pending permissions ───────────────────────────────────

    @property
    def pending_permissions(
        self,
    ) -> dict[str, tuple[asyncio.Event, str, str, bool | None, str | None]]:
        return self._pending_permissions

    # ── Session lifecycle ─────────────────────────────────────

    def load(
        self,
        session_id: str,
        session_manager: SessionManager,
        context_size: int,
    ) -> AgentState | None:
        if session_id in self._states:
            return self._states[session_id]
        loaded = session_manager.load_state(session_id)
        if loaded is None:
            return None
        system_message = loaded.messages[0] if loaded.messages else None
        if system_message and isinstance(system_message, SystemMessage):
            compressed = session_manager.load_compressed_state(
                session_id,
                system_message,
                context_size,
            )
            if compressed is not None:
                loaded = compressed
        if loaded.usage:
            loaded.usage.context_size = context_size
        self._states[session_id] = loaded
        return loaded

    def fork(
        self,
        session_id: str,
        session_manager: SessionManager,
    ) -> str | None:
        state = self._states.get(session_id)
        if state is None or not state.session_id:
            return None
        child = session_manager.fork(state.session_id)
        forked = copy.deepcopy(state)
        forked.session_id = SessionID(child.id)
        self._states[child.id] = forked
        return child.id

    def save_all(self, session_manager: SessionManager) -> None:
        for sid, state in list(self._states.items()):
            save_id = state.session_id or sid
            if session_manager.get(save_id):
                session_manager.save_state(save_id, state)
                logger.info(f"Session state saved: {sid} (session_id={save_id})")
        self._states.clear()
