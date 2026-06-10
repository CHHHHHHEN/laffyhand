from __future__ import annotations

import asyncio

import pytest

from laffyhand.core.event_bus import SessionEventBus
from laffyhand.core.models import TextDelta


@pytest.fixture
def bus() -> SessionEventBus:
    return SessionEventBus()


class TestSessionEventBus:
    @pytest.mark.anyio
    async def test_subscribe_and_publish(self, bus: SessionEventBus) -> None:
        async with bus.subscribe("sess-1") as stream:
            await bus.publish(
                "sess-1", TextDelta(id="1", text="hello")
            )

            result = await asyncio.wait_for(stream.__anext__(), timeout=1)
            assert isinstance(result, TextDelta)
            assert result.text == "hello"

    @pytest.mark.anyio
    async def test_publish_fan_out_to_multiple_subscribers(
        self, bus: SessionEventBus,
    ) -> None:
        async def collect(sid: str) -> list:
            results = []
            async with bus.subscribe(sid) as stream:
                results.append(await asyncio.wait_for(stream.__anext__(), timeout=1))
                results.append(await asyncio.wait_for(stream.__anext__(), timeout=1))
            return results

        async def publish() -> None:
            await asyncio.sleep(0.05)
            await bus.publish("sess-1", TextDelta(id="1", text="first"))
            await bus.publish("sess-1", TextDelta(id="1", text="second"))

        async with asyncio.TaskGroup() as tg:
            collector = tg.create_task(collect("sess-1"))
            tg.create_task(publish())

        assert len(collector.result()) == 2
        assert collector.result()[0].text == "first"
        assert collector.result()[1].text == "second"

    @pytest.mark.anyio
    async def test_publish_only_target_session(self, bus: SessionEventBus) -> None:
        async with bus.subscribe("sess-1") as s1:
            async with bus.subscribe("sess-2") as s2:
                await bus.publish(
                    "sess-1", TextDelta(id="1", text="hello")
                )

                r1 = await asyncio.wait_for(s1.__anext__(), timeout=1)
                assert isinstance(r1, TextDelta)
                assert r1.text == "hello"

                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(s2.__anext__(), timeout=0.1)

    @pytest.mark.anyio
    async def test_close_session_sends_sentinel(self, bus: SessionEventBus) -> None:
        async with bus.subscribe("sess-1") as stream:
            await bus.close_session("sess-1")

            with pytest.raises(StopAsyncIteration):
                await asyncio.wait_for(stream.__anext__(), timeout=1)

    @pytest.mark.anyio
    async def test_close_session_removes_subscribers(
        self, bus: SessionEventBus,
    ) -> None:
        async with bus.subscribe("sess-1"):
            pass

        assert await bus.has_subscribers("sess-1") is False

    @pytest.mark.anyio
    async def test_has_subscribers(self, bus: SessionEventBus) -> None:
        assert await bus.has_subscribers("sess-1") is False

        async with bus.subscribe("sess-1"):
            assert await bus.has_subscribers("sess-1") is True

    @pytest.mark.anyio
    async def test_close_session_unblocks_waiting_subscriber(
        self, bus: SessionEventBus,
    ) -> None:
        async def close() -> None:
            await asyncio.sleep(0.05)
            await bus.close_session("sess-1")

        async def read() -> None:
            async with bus.subscribe("sess-1") as stream:
                with pytest.raises(StopAsyncIteration):
                    await asyncio.wait_for(stream.__anext__(), timeout=5)

        async with asyncio.TaskGroup() as tg:
            tg.create_task(close())
            tg.create_task(read())
