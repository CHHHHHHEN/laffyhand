from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from laffyhand.gateway.dispatcher import Dispatcher, RegisteredHandler
from laffyhand.gateway.protocol import Request


@pytest.fixture
def dispatcher(runtime):
    return Dispatcher(runtime=runtime)


class TestRegister:
    def test_registers_handler(self, dispatcher):
        async def handler(*args):
            return {"ok": True}

        dispatcher.register("test", handler)
        assert "test" in dispatcher.handlers
        assert dispatcher.handlers["test"].func is handler
        assert dispatcher.handlers["test"].streaming is False

    def test_registers_streaming_handler(self, dispatcher):
        async def handler(*args):
            return None

        dispatcher.register("stream", handler, streaming=True)
        assert dispatcher.handlers["stream"].streaming is True

    def test_overwrites_existing(self, dispatcher):
        async def h1(*args):
            return 1

        async def h2(*args):
            return 2

        dispatcher.register("x", h1)
        dispatcher.register("x", h2)
        assert dispatcher.handlers["x"].func is h2


class TestDispatch:
    @pytest.mark.anyio
    async def test_calls_handler_with_correct_args(self, dispatcher, transport):
        handler = AsyncMock(return_value={"ok": True})
        dispatcher.register("test", handler)
        req = Request(id=1, method="test", params={"a": 1})

        await dispatcher.dispatch(req, transport, "conn-1")

        handler.assert_awaited_once()
        args = handler.call_args[0]
        assert args[0] is dispatcher.runtime
        assert args[1] == {"a": 1}
        assert args[2] is transport
        assert args[3] == 1
        assert args[4] == "conn-1"

    @pytest.mark.anyio
    async def test_sends_result_for_non_streaming(self, dispatcher, transport):
        handler = AsyncMock(return_value={"ok": True})
        dispatcher.register("test", handler)
        req = Request(id=1, method="test")

        await dispatcher.dispatch(req, transport, "c")

        transport.send.assert_awaited_once()
        sent = json.loads(transport.send.call_args[0][0])
        assert sent["jsonrpc"] == "2.0"
        assert sent["id"] == 1
        assert sent["result"] == {"ok": True}

    @pytest.mark.anyio
    async def test_does_not_send_result_for_streaming(self, dispatcher, transport):
        handler = AsyncMock(return_value=None)
        dispatcher.register("stream", handler, streaming=True)
        req = Request(id=1, method="stream")

        await dispatcher.dispatch(req, transport, "c")

        transport.send.assert_not_called()

    @pytest.mark.anyio
    async def test_method_not_found(self, dispatcher, transport):
        req = Request(id=1, method="nonexistent")

        await dispatcher.dispatch(req, transport, "c")

        transport.send.assert_awaited_once()
        sent = json.loads(transport.send.call_args[0][0])
        assert sent["error"]["code"] == -32601
        assert "not found" in sent["error"]["message"].lower()

    @pytest.mark.anyio
    async def test_handler_exception_returns_internal_error(
        self, dispatcher, transport
    ):
        async def failing(*args):
            raise RuntimeError("boom")

        dispatcher.register("fail", failing)
        req = Request(id=1, method="fail")

        await dispatcher.dispatch(req, transport, "c")

        transport.send.assert_awaited_once()
        sent = json.loads(transport.send.call_args[0][0])
        assert sent["error"]["code"] == -32603
        assert sent["error"]["message"] == "Internal error"

    @pytest.mark.anyio
    async def test_sets_shutdown_requested(self, dispatcher, transport):
        handler = AsyncMock(return_value=None)
        dispatcher.register("shutdown", handler)
        req = Request(id=1, method="shutdown")

        await dispatcher.dispatch(req, transport, "c")

        assert dispatcher.shutdown_requested is True

    @pytest.mark.anyio
    async def test_does_not_set_shutdown_on_other_methods(self, dispatcher, transport):
        handler = AsyncMock(return_value={})
        dispatcher.register("chat", handler)
        req = Request(id=1, method="chat")

        await dispatcher.dispatch(req, transport, "c")

        assert dispatcher.shutdown_requested is False

    @pytest.mark.anyio
    async def test_empty_params_defaults_to_empty_dict(self, dispatcher, transport):
        handler = AsyncMock(return_value={})
        dispatcher.register("test", handler)
        req = Request(id=1, method="test", params=None)

        await dispatcher.dispatch(req, transport, "c")

        assert handler.call_args[0][1] == {}


class TestRegisteredHandler:
    def test_default_streaming_false(self):
        async def h(*args):
            pass

        r = RegisteredHandler(func=h)
        assert r.streaming is False

    def test_custom_streaming(self):
        async def h(*args):
            pass

        r = RegisteredHandler(func=h, streaming=True)
        assert r.streaming is True
