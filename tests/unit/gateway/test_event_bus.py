from __future__ import annotations

import asyncio
from typing import Any

import pytest

from laffyhand.core.event_bus import SessionEventBus


@pytest.fixture
def bus() -> SessionEventBus:
    return SessionEventBus()


class TestSessionEventBus:
    @pytest.mark.anyio
    async def test_subscribe_and_publish(self, bus: SessionEventBus) -> None:
        q = await bus.subscribe("sess-1")
        await bus.publish("sess-1", {"type": "text-delta", "text": "hello"})

        result = await asyncio.wait_for(q.get(), timeout=1)
        assert result == {"type": "text-delta", "text": "hello"}

    @pytest.mark.anyio
    async def test_publish_fan_out_to_multiple_subscribers(
        self, bus: SessionEventBus,
    ) -> None:
        q1 = await bus.subscribe("sess-1")
        q2 = await bus.subscribe("sess-1")

        await bus.publish("sess-1", {"type": "finish"})

        r1 = await asyncio.wait_for(q1.get(), timeout=1)
        r2 = await asyncio.wait_for(q2.get(), timeout=1)
        assert r1 == {"type": "finish"}
        assert r2 == {"type": "finish"}

    @pytest.mark.anyio
    async def test_publish_only_target_session(self, bus: SessionEventBus) -> None:
        q1 = await bus.subscribe("sess-1")
        q2 = await bus.subscribe("sess-2")

        await bus.publish("sess-1", {"type": "text-delta", "text": "hello"})

        r1 = await asyncio.wait_for(q1.get(), timeout=1)
        assert r1 == {"type": "text-delta", "text": "hello"}

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(q2.get(), timeout=0.1)

    @pytest.mark.anyio
    async def test_close_session_sends_sentinel(self, bus: SessionEventBus) -> None:
        q = await bus.subscribe("sess-1")
        await bus.close_session("sess-1")

        result = await asyncio.wait_for(q.get(), timeout=1)
        assert result is None

    @pytest.mark.anyio
    async def test_close_session_removes_queues(self, bus: SessionEventBus) -> None:
        await bus.subscribe("sess-1")
        await bus.close_session("sess-1")
        assert await bus.has_subscribers("sess-1") is False

    @pytest.mark.anyio
    async def test_unsubscribe_removes_queue(self, bus: SessionEventBus) -> None:
        q = await bus.subscribe("sess-1")
        await bus.unsubscribe("sess-1", q)
        assert await bus.has_subscribers("sess-1") is False

    @pytest.mark.anyio
    async def test_has_subscribers(self, bus: SessionEventBus) -> None:
        assert await bus.has_subscribers("sess-1") is False

        await bus.subscribe("sess-1")
        assert await bus.has_subscribers("sess-1") is True

    @pytest.mark.anyio
    async def test_close_session_unblocks_waiting_subscriber(
        self, bus: SessionEventBus,
    ) -> None:
        q = await bus.subscribe("sess-1")

        async def delayed_close() -> None:
            await asyncio.sleep(0.05)
            await bus.close_session("sess-1")

        async def reader() -> dict[str, Any] | None:
            return await q.get()

        async with asyncio.TaskGroup() as tg:
            t1 = tg.create_task(reader())
            tg.create_task(delayed_close())
            result = await t1

        assert result is None
