from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


from loguru import logger

from laffyhand.core.models import AgentEvent


class _Subscriber:
    def __init__(self, is_primary: bool = False, maxsize: int = 0) -> None:
        self.queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue(maxsize)
        self.is_primary = is_primary
        self._closed = False

    def try_put(self, event: AgentEvent) -> bool:
        if self._closed:
            return False
        try:
            self.queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            return False

    async def put(self, event: AgentEvent) -> None:
        if self._closed:
            return
        await self.queue.put(event)

    def close(self) -> None:
        self._closed = True


class SessionEventBus:
    """Per-session event bus for fan-out to multiple subscribers.

    Each session has a list of subscriber queues. When ``publish`` is called,
    the event is pushed to every subscriber queue.

    * Primary subscriber — uses ``await put()``, applies backpressure.
    * Secondary subscribers — use ``try_put()``, silently drop on overflow.
    """

    def __init__(self) -> None:
        self._subs: dict[str, list[_Subscriber]] = {}
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def subscribe(
        self,
        session_id: str,
        is_primary: bool = False,
    ) -> AsyncIterator[AsyncIterator[AgentEvent]]:
        """Subscribe to events for a session.

        Usage::

            async with event_bus.subscribe(sid) as stream:
                async for event in stream:
                    ...
        """
        sub = _Subscriber(is_primary=is_primary)
        async with self._lock:
            self._subs.setdefault(session_id, []).append(sub)
        logger.debug(f"SessionEventBus: subscriber added for {session_id}")

        async def _iter() -> AsyncIterator[AgentEvent]:
            try:
                while True:
                    event = await sub.queue.get()
                    if event is None:
                        break
                    yield event
            finally:
                await self._unsubscribe(session_id, sub)

        try:
            yield _iter()
        finally:
            sub.queue.put_nowait(None)
            sub.close()
            await self._unsubscribe(session_id, sub)

    async def _unsubscribe(self, session_id: str, sub: _Subscriber) -> None:
        async with self._lock:
            subs = self._subs.get(session_id, [])
            if sub in subs:
                subs.remove(sub)
        logger.debug(f"SessionEventBus: subscriber removed for {session_id}")

    async def publish(self, session_id: str, event: AgentEvent) -> None:
        """Publish an event to all subscribers of a session.

        Primary subscribers receive the event with backpressure (the producer
        will wait until the event is consumed). Secondary subscribers receive
        the event in a non-blocking fashion — if their queue is full the event
        is silently dropped.
        """
        async with self._lock:
            subs = list(self._subs.get(session_id, []))

        for sub in subs:
            if sub.is_primary:
                await sub.put(event)
            else:
                sub.try_put(event)

    async def close_session(self, session_id: str) -> None:
        """Close a session and send sentinel to all subscribers."""
        async with self._lock:
            subs = self._subs.pop(session_id, [])
        for sub in subs:
            sub.queue.put_nowait(None)
        logger.debug(
            f"SessionEventBus: session {session_id} closed ({len(subs)} subscriber(s))"
        )

    async def has_subscribers(self, session_id: str) -> bool:
        async with self._lock:
            subs = self._subs.get(session_id, [])
            return len(subs) > 0
