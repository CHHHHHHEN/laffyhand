from __future__ import annotations

from asyncio import timeout as asyncio_timeout

import pytest

from laffyhand.gateway.transport import InProcessTransport, _NullTransport


class TestInProcessTransport:
    @pytest.mark.anyio
    async def test_create_pair_roundtrip(self):
        server, client = InProcessTransport.create_pair()
        await client.send("hello from client")
        received = await server.recv()
        assert received == "hello from client"

        await server.send("hello from server")
        received = await client.recv()
        assert received == "hello from server"

    @pytest.mark.anyio
    async def test_multiple_messages(self):
        server, client = InProcessTransport.create_pair()
        await client.send("msg1")
        await client.send("msg2")
        assert await server.recv() == "msg1"
        assert await server.recv() == "msg2"

    @pytest.mark.anyio
    async def test_close_stops_send(self):
        server, client = InProcessTransport.create_pair()
        await server.close()
        await server.send("should not appear")
        with pytest.raises(TimeoutError):
            async with asyncio_timeout(0.05):
                await client.recv()

    @pytest.mark.anyio
    async def test_close_returns_empty_on_recv(self):
        server, client = InProcessTransport.create_pair()
        await server.close()
        result = await server.recv()
        assert result == ""

    @pytest.mark.anyio
    async def test_independent_queues(self):
        server, client = InProcessTransport.create_pair()
        await client.send("c2s")
        await server.send("s2c")
        assert await server.recv() == "c2s"
        assert await client.recv() == "s2c"


class TestNullTransport:
    @pytest.mark.anyio
    async def test_send_noop(self):
        t = _NullTransport()
        await t.send("anything")
        assert True

    @pytest.mark.anyio
    async def test_recv_returns_empty(self):
        t = _NullTransport()
        result = await t.recv()
        assert result == ""

    @pytest.mark.anyio
    async def test_close_noop(self):
        t = _NullTransport()
        await t.close()
        assert True

    def test_connection_id(self):
        t = _NullTransport()
        assert t.connection_id == "null"
