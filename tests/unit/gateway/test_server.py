from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from laffyhand.gateway.server import GatewayServer
from laffyhand.gateway.protocol import Request


@pytest.fixture
def transport():
    t = MagicMock()
    t.connection_id = "test-conn"
    t.send = AsyncMock()
    t.recv = AsyncMock()
    t.close = AsyncMock()
    return t


@pytest.fixture
def server(runtime, transport):
    return GatewayServer(runtime, transport)


class TestGatewayServer:
    @pytest.mark.anyio
    async def test_serve_processes_request(self, server, transport):
        req = Request(id=1, method="initialize", params={})
        transport.recv = AsyncMock(side_effect=[req.json(), ""])

        await server.serve()

        transport.send.assert_called_once()

    @pytest.mark.anyio
    async def test_serve_handles_parse_error(self, server, transport):
        transport.recv = AsyncMock(side_effect=["invalid json", ""])

        await server.serve()

        transport.send.assert_called_once()
        sent = json.loads(transport.send.call_args[0][0])
        assert sent["error"]["code"] == -32700

    @pytest.mark.anyio
    async def test_serve_breaks_on_empty_message(self, server, transport):
        transport.recv = AsyncMock(return_value="")

        await server.serve()

        transport.send.assert_not_called()

    @pytest.mark.anyio
    async def test_serve_ignores_notifications(self, server, transport):
        notif = '{"jsonrpc":"2.0","method":"some_event"}'
        transport.recv = AsyncMock(side_effect=[notif, ""])

        await server.serve()

        transport.send.assert_not_called()

    @pytest.mark.anyio
    async def test_shutdown_requested_stops_loop(self, server, transport):
        server._ensure_handlers()
        server.dispatcher.handlers["shutdown"].func = AsyncMock(return_value=None)

        req = Request(id=1, method="shutdown", params={})
        transport.recv = AsyncMock(side_effect=[req.json(), ""])

        await server.serve()

        assert server.dispatcher.shutdown_requested is True

    @pytest.mark.anyio
    async def test_shutdown_called_on_exit(self, server, transport):
        transport.recv = AsyncMock(return_value="")
        server.shutdown = AsyncMock(wraps=server.shutdown)

        await server.serve()

        server.shutdown.assert_awaited_once()

    @pytest.mark.anyio
    async def test_ensure_handlers_registered_once(self, server):
        assert server._handlers_registered is False
        server._ensure_handlers()
        assert server._handlers_registered is True
        assert len(server.dispatcher.handlers) > 0

        n_before = len(server.dispatcher.handlers)
        server._ensure_handlers()
        assert len(server.dispatcher.handlers) == n_before

    def test_stop_sets_running_false(self, server):
        server._running = True
        server.stop()
        assert server._running is False

    @pytest.mark.anyio
    async def test_serve_sanitizes_error_response(self, server, transport):
        transport.recv = AsyncMock(side_effect=["invalid json", ""])

        await server.serve()

        sent = json.loads(transport.send.call_args[0][0])
        assert sent["error"]["message"] == "Parse error"
        assert "invalid" not in sent["error"]["message"].lower()

    @pytest.mark.anyio
    async def test_serve_handles_transport_exception(self, server, transport):
        transport.recv = AsyncMock(side_effect=RuntimeError("transport failed"))

        await server.serve()

        assert server._running is False
