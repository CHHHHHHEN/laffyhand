from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger


class SessionEventBus:
    """Per-session event bus for fan-out to multiple SSE subscribers.

    Each session has a list of subscriber queues. When ``publish`` is called,
    the event dict is pushed to every subscriber queue. Subscribers receive
    events via ``subscribe()`` and must call ``unsubscribe()`` to clean up.
    """

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[dict[str, Any] | None]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self, session_id: str,
    ) -> asyncio.Queue[dict[str, Any] | None]:
        q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        async with self._lock:
            self._queues.setdefault(session_id, []).append(q)
        logger.debug(f"SessionEventBus: subscriber added for {session_id}")
        return q

    async def unsubscribe(
        self,
        session_id: str,
        q: asyncio.Queue[dict[str, Any] | None],
    ) -> None:
        async with self._lock:
            queues = self._queues.get(session_id, [])
            if q in queues:
                queues.remove(q)
        logger.debug(f"SessionEventBus: subscriber removed for {session_id}")

    async def publish(self, session_id: str, event: dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._queues.get(session_id, []))
        for q in queues:
            q.put_nowait(event)

    async def close_session(self, session_id: str) -> None:
        async with self._lock:
            queues = self._queues.pop(session_id, [])
        for q in queues:
            q.put_nowait(None)
        logger.debug(f"SessionEventBus: session {session_id} closed ({len(queues)} subscriber(s))")

    async def has_subscribers(self, session_id: str) -> bool:
        async with self._lock:
            queues = self._queues.get(session_id, [])
            return len(queues) > 0
