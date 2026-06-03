from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def runtime():
    r = MagicMock()
    r.current_session_id = "sess-1"
    return r


@pytest.fixture
def http_transport(runtime):
    from laffyhand.gateway.http_transport import HTTPTransport

    return HTTPTransport(runtime=runtime)


def _make_sse_request() -> MagicMock:
    """Create a mock aiohttp Request suitable for SSE stream tests."""
    import aiohttp

    req = MagicMock()
    req.headers = {"Origin": "http://localhost:1420", "Accept": "text/event-stream"}
    req.version = aiohttp.HttpVersion11
    req.get_extra_info = MagicMock(return_value=None)
    # aiohttp StreamResponse.prepare() calls request._prepare_hook(response)
    req._prepare_hook = AsyncMock()
    return req


class TestCorsResolution:
    def test_allowed_origin(self):
        from laffyhand.gateway.http_transport import _resolve_cors_origin

        assert _resolve_cors_origin("http://localhost:1420") == "http://localhost:1420"
        assert _resolve_cors_origin("http://127.0.0.1:1420") == "http://127.0.0.1:1420"

    def test_default_origin(self):
        from laffyhand.gateway.http_transport import _resolve_cors_origin

        assert _resolve_cors_origin("http://evil.com") == "http://localhost:1420"
        assert _resolve_cors_origin(None) == "http://localhost:1420"

    def test_cors_headers(self):
        from laffyhand.gateway.http_transport import _cors_headers

        headers = _cors_headers("http://localhost:1420")
        assert headers["Access-Control-Allow-Origin"] == "http://localhost:1420"
        assert "POST, GET, OPTIONS" in headers["Access-Control-Allow-Methods"]


class TestHttpStreamTransport:
    @pytest.mark.anyio
    async def test_send_writes_sse_format(self):
        from laffyhand.gateway.http_transport import _HTTPStreamTransport

        mock_response = AsyncMock()
        transport = _HTTPStreamTransport(mock_response, "conn-1")
        await transport.send('{"key": "value"}')
        mock_response.write.assert_awaited_once_with(b'data: {"key": "value"}\n\n')

    @pytest.mark.anyio
    async def test_send_respects_closed(self):
        from laffyhand.gateway.http_transport import _HTTPStreamTransport

        mock_response = AsyncMock()
        transport = _HTTPStreamTransport(mock_response, "conn-1")
        transport._closed = True
        await transport.send("data")
        mock_response.write.assert_not_called()

    @pytest.mark.anyio
    async def test_send_sets_closed_on_error(self):
        from laffyhand.gateway.http_transport import _HTTPStreamTransport

        mock_response = AsyncMock()
        mock_response.write = AsyncMock(side_effect=ConnectionError("broken pipe"))
        transport = _HTTPStreamTransport(mock_response, "conn-1")
        await transport.send("data")
        assert transport._closed is True

    def test_recv_returns_empty(self):
        from laffyhand.gateway.http_transport import _HTTPStreamTransport

        import anyio

        mock_response = MagicMock()
        transport = _HTTPStreamTransport(mock_response, "conn-1")
        assert anyio.run(transport.recv) == ""

    def test_transport_has_dispatcher_and_canceller(self):
        from laffyhand.gateway.http_transport import _HTTPStreamTransport

        mock_response = MagicMock()
        transport = _HTTPStreamTransport(mock_response, "conn-1", dispatcher="d1")
        assert transport._dispatcher == "d1"
        assert transport.connection_id == "conn-1"


class TestSetupRoutes:
    def test_setup_routes_adds_three_endpoints(self, http_transport):
        app = MagicMock()
        http_transport.setup_routes(app)
        assert app.router.add_post.call_count == 1
        assert app.router.add_get.call_count == 1
        assert app.router.add_options.call_count == 1

    def test_setup_routes_adds_correct_paths(self, http_transport):
        app = MagicMock()
        http_transport.setup_routes(app)
        # Verify the /rpc POST route
        app.router.add_post.assert_called_once_with("/rpc", http_transport._handle_rpc)
        # Verify the /health GET route
        app.router.add_get.assert_any_call("/health", http_transport._handle_health)
        # Verify the /rpc OPTIONS route
        app.router.add_options.assert_called_once_with(
            "/rpc", http_transport._handle_cors_preflight
        )


class TestCorsPreflight:
    @pytest.mark.anyio
    async def test_returns_204_with_cors(self, http_transport):
        request = MagicMock()
        request.headers.get = MagicMock(return_value="http://localhost:1420")
        response = await http_transport._handle_cors_preflight(request)
        assert response.status == 204
        assert (
            response.headers["Access-Control-Allow-Origin"] == "http://localhost:1420"
        )


class TestHandleHealth:
    @pytest.mark.anyio
    async def test_returns_ok(self, http_transport):
        request = MagicMock()
        request.headers.get = MagicMock(return_value="http://localhost:1420")
        response = await http_transport._handle_health(request)
        body = json.loads(response.body)
        assert body["status"] == "ok"
        assert (
            response.headers["Access-Control-Allow-Origin"] == "http://localhost:1420"
        )


class TestHandleRpcParseError:
    @pytest.mark.anyio
    async def test_empty_body_returns_400(self, http_transport):
        request = MagicMock()
        request.read = AsyncMock(return_value=b"")
        request.headers.get = MagicMock(return_value=None)
        response = await http_transport._handle_rpc(request)
        assert response.status == 400
        body = json.loads(response.body)
        assert body["error"]["code"] == -32700

    @pytest.mark.anyio
    async def test_invalid_json_returns_400(self, http_transport):
        request = MagicMock()
        request.read = AsyncMock(return_value=b"not json")
        request.headers.get = MagicMock(return_value=None)
        response = await http_transport._handle_rpc(request)
        assert response.status == 400
        body = json.loads(response.body)
        assert body["error"]["code"] == -32700


class TestHandleRpcCall:
    @pytest.mark.anyio
    async def test_non_streaming_call(self, http_transport):
        """A non-streaming RPC call invokes the handler and returns JSON."""
        from laffyhand.gateway.dispatcher import RegisteredHandler

        handler_fn = AsyncMock(return_value={"result_key": "value"})
        entry = RegisteredHandler(func=handler_fn, streaming=False)
        message = MagicMock()
        message.method = "session/list"
        message.id = 42
        message.params = {"limit": 10}

        response = await http_transport._handle_rpc_call(
            message,
            entry,
            http_transport._dispatcher,
            "http://localhost:1420",
        )
        assert response.status == 200
        body = json.loads(response.body)
        assert body["id"] == 42
        assert body["result"]["result_key"] == "value"
        handler_fn.assert_awaited_once()

    @pytest.mark.anyio
    async def test_cancel_call_attaches_sse_canceller(self, http_transport):
        """chat/cancel calls should attach _sse_canceller to the transport."""
        from laffyhand.gateway.dispatcher import RegisteredHandler

        handler_fn = AsyncMock(return_value={"status": "cancelled"})
        entry = RegisteredHandler(func=handler_fn, streaming=False)
        message = MagicMock()
        message.method = "chat/cancel"
        message.id = 99
        message.params = {}

        await http_transport._handle_rpc_call(
            message,
            entry,
            http_transport._dispatcher,
            "http://localhost:1420",
        )

        # Verify the handler was called with a transport that has sse_canceller
        _, kwargs = handler_fn.call_args
        transport_arg = kwargs.get("transport") or handler_fn.call_args[0][2]
        assert hasattr(transport_arg, "sse_canceller")
        assert transport_arg.sse_canceller == http_transport._cancel_sse_task

    @pytest.mark.anyio
    async def test_handler_error_returns_500(self, http_transport):
        from laffyhand.gateway.dispatcher import RegisteredHandler

        handler_fn = AsyncMock(side_effect=ValueError("bad params"))
        entry = RegisteredHandler(func=handler_fn, streaming=False)
        message = MagicMock()
        message.method = "session/load"
        message.id = 1
        message.params = {}

        response = await http_transport._handle_rpc_call(
            message,
            entry,
            http_transport._dispatcher,
            "http://localhost:1420",
        )
        assert response.status == 200
        body = json.loads(response.body)
        assert body["error"]["code"] == -32000
        assert body["error"]["message"] == "bad params"


class TestSseTaskTracking:
    @pytest.mark.anyio
    async def test_cancel_sse_task_cancels_all_when_conn_id_is_http(
        self, http_transport
    ):
        """_cancel_sse_task with conn_id='http' cancels all tracked SSE tasks."""
        task1 = asyncio_task_mock()
        task2 = asyncio_task_mock()
        http_transport._sse_tasks["conn-a"] = task1
        http_transport._sse_tasks["conn-b"] = task2

        result = http_transport._cancel_sse_task("http")

        assert result is True
        task1.cancel.assert_called_once()
        task2.cancel.assert_called_once()

    @pytest.mark.anyio
    async def test_cancel_sse_task_cancels_specific(self, http_transport):
        """_cancel_sse_task with a specific conn_id cancels only that task."""
        task1 = asyncio_task_mock()
        task2 = asyncio_task_mock()
        http_transport._sse_tasks["conn-a"] = task1
        http_transport._sse_tasks["conn-b"] = task2

        result = http_transport._cancel_sse_task("conn-a")

        assert result is True
        task1.cancel.assert_called_once()
        task2.cancel.assert_not_called()

    @pytest.mark.anyio
    async def test_cancel_sse_task_returns_false_when_no_tasks(self, http_transport):
        result = http_transport._cancel_sse_task("http")
        assert result is False

    @pytest.mark.anyio
    async def test_cancel_sse_task_skips_done_tasks(self, http_transport):
        """When all tasks are already done, cancel returns False."""
        from asyncio import Task

        task = MagicMock(spec=Task)
        task.done.return_value = True
        http_transport._sse_tasks["conn-a"] = task

        result = http_transport._cancel_sse_task("http")

        assert result is False
        task.cancel.assert_not_called()

    @pytest.mark.anyio
    async def test_close_cancels_pending_sse_tasks(self, http_transport):
        """close() should cancel all pending SSE tasks before cleanup."""
        task = asyncio_task_mock()
        http_transport._sse_tasks["conn-x"] = task
        http_transport._runner = MagicMock()
        http_transport._runner.cleanup = AsyncMock()

        await http_transport.close()

        task.cancel.assert_called_once()
        http_transport._runner.cleanup.assert_awaited_once()

    @pytest.mark.anyio
    async def test_close_without_runner(self, http_transport):
        """close() should not crash if runner was never set up."""
        task = asyncio_task_mock()
        http_transport._sse_tasks["conn-x"] = task

        await http_transport.close()

        task.cancel.assert_called_once()


def asyncio_task_mock():
    """Create a MagicMock that looks like an asyncio.Task (not done)."""
    from asyncio import Task

    t = MagicMock(spec=Task)
    t.done.return_value = False
    t.cancel = MagicMock()
    return t


class TestSseStreamHandler:
    @pytest.mark.anyio
    async def test_sse_stream_tracks_task(self, http_transport):
        """SSE stream handler should register the task in _sse_tasks and clean up on completion."""

        from laffyhand.gateway.dispatcher import RegisteredHandler

        handler_fn = AsyncMock()
        entry = RegisteredHandler(func=handler_fn, streaming=True)
        message = MagicMock()
        message.method = "chat/stream"
        message.id = 1
        message.params = {"message": "hello"}

        with (
            patch("aiohttp.web.StreamResponse.prepare", return_value=None),
            patch("aiohttp.web.StreamResponse.write_eof", return_value=None),
        ):
            response = await http_transport._handle_sse_stream(
                _make_sse_request(),
                message,
                entry,
                http_transport._dispatcher,
                "http://localhost:1420",
            )

        # After the stream completes, the task should have been added then cleaned up
        assert len(http_transport._sse_tasks) == 0
        assert response.status == 200

    @pytest.mark.anyio
    async def test_sse_stream_attaches_canceller(self, http_transport):
        """SSE stream transport should have _sse_canceller attached."""

        from laffyhand.gateway.dispatcher import RegisteredHandler

        captured_transport = {}

        async def capture_handler(*args, **kwargs):
            captured_transport["transport"] = args[2]

        entry = RegisteredHandler(func=capture_handler, streaming=True)
        message = MagicMock()
        message.method = "chat/stream"
        message.id = 1
        message.params = {"message": "hi"}

        with (
            patch("aiohttp.web.StreamResponse.prepare", return_value=None),
            patch("aiohttp.web.StreamResponse.write_eof", return_value=None),
        ):
            await http_transport._handle_sse_stream(
                _make_sse_request(),
                message,
                entry,
                http_transport._dispatcher,
                "http://localhost:1420",
            )

        transport = captured_transport["transport"]
        assert hasattr(transport, "sse_canceller")
        assert transport.sse_canceller == http_transport._cancel_sse_task
