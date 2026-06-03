from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from laffyhand.gateway.protocol import MAX_MESSAGE_SIZE, SESSION_ALREADY_STREAMING
from laffyhand.gateway.transport import Transport, _NullTransport

if TYPE_CHECKING:
    import aiohttp.web
    from laffyhand.agent.runtime import AgentRuntime
    from laffyhand.gateway.dispatcher import Dispatcher, RegisteredHandler
    from laffyhand.gateway.protocol import Request
    from laffyhand.gateway.server import GatewayServer


# Default CORS origin for Vite dev server (port 1420).
# Production: UI served from the same host:port -> same-origin -> CORS irrelevant.
ALLOWED_CORS_ORIGINS = frozenset(
    {
        "http://localhost:1420",
        "http://127.0.0.1:1420",
    }
)
_DEFAULT_CORS_ORIGIN = "http://localhost:1420"


def _resolve_cors_origin(request_origin: str | None) -> str:
    if request_origin in ALLOWED_CORS_ORIGINS:
        return request_origin
    return _DEFAULT_CORS_ORIGIN


def _cors_headers(origin: str = _DEFAULT_CORS_ORIGIN) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Accept",
        "Access-Control-Max-Age": "86400",
    }


def _json_response(
    data: dict[str, Any], status: int = 200, origin: str = _DEFAULT_CORS_ORIGIN
) -> aiohttp.web.StreamResponse:
    import aiohttp.web

    return aiohttp.web.json_response(data, status=status, headers=_cors_headers(origin))


class _WSConnection(Transport):
    def __init__(self, ws: aiohttp.web.WebSocketResponse, conn_id: str) -> None:
        from aiohttp import WSMsgType

        self._ws = ws
        self.connection_id = conn_id
        self._closed = False
        self._WSMsgType = WSMsgType

    async def send(self, data: str) -> None:
        if self._closed:
            return
        try:
            await self._ws.send_str(data)
        except Exception:
            self._closed = True

    async def recv(self) -> str:
        if self._closed:
            return ""
        try:
            msg = await self._ws.receive()
            if msg.type == self._WSMsgType.TEXT:
                return cast(str, msg.data)
            if msg.type in (
                self._WSMsgType.BINARY,
                self._WSMsgType.CLOSE,
                self._WSMsgType.PING,
                self._WSMsgType.PONG,
            ):
                self._closed = True
                return ""
            return ""
        except Exception:
            self._closed = True
            return ""

    async def close(self) -> None:
        self._closed = True
        try:
            await self._ws.close()
        except Exception:
            pass


class WSTransport:
    """WebSocket transport — each client gets a dedicated GatewayServer."""

    def __init__(
        self,
        runtime: AgentRuntime | None = None,
        host: str = "127.0.0.1",
        port: int = 9090,
    ) -> None:
        self.runtime = runtime
        self.host = host
        self.port = port
        self._runner: aiohttp.web.AppRunner | None = None
        self._gateway_servers: list[GatewayServer] = []

    async def start(self) -> None:
        import aiohttp.web

        app = aiohttp.web.Application()
        app.router.add_get("/ws", self._handle_ws)
        app.router.add_get("/health", self._handle_health)
        runner = aiohttp.web.AppRunner(app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, self.host, self.port)
        await site.start()
        self._runner = runner
        logger.info(f"WebSocket transport listening on ws://{self.host}:{self.port}/ws")

    async def _handle_ws(
        self, request: aiohttp.web.Request
    ) -> aiohttp.web.WebSocketResponse:
        import aiohttp.web

        ws = aiohttp.web.WebSocketResponse(max_msg_size=16 * 1024 * 1024)
        await ws.prepare(request)
        conn_id = f"ws_{id(ws):x}"
        transport = _WSConnection(ws, conn_id)

        from laffyhand.gateway.server import GatewayServer

        gateway = GatewayServer(self.runtime, transport)

        self._gateway_servers.append(gateway)
        try:
            logger.info(f"WebSocket client connected: {conn_id}")
            await gateway.serve()
        finally:
            self._gateway_servers.remove(gateway)
            logger.info(f"WebSocket client disconnected: {conn_id}")

        return ws

    async def _handle_health(
        self, request: aiohttp.web.Request
    ) -> aiohttp.web.StreamResponse:
        origin = _resolve_cors_origin(request.headers.get("Origin"))
        return _json_response({"status": "ok"}, origin=origin)

    async def close(self) -> None:
        for g in list(self._gateway_servers):
            g.stop()
        if self._runner:
            await self._runner.cleanup()


class _HTTPStreamTransport(Transport):
    """Transport wrapping an SSE StreamResponse — used per streaming request."""

    def __init__(
        self,
        response: aiohttp.web.StreamResponse,
        conn_id: str,
        dispatcher: Dispatcher | None = None,
    ) -> None:
        self._response = response
        self.connection_id = conn_id
        self._closed = False
        self._dispatcher = dispatcher

    async def send(self, data: str) -> None:
        if self._closed:
            return
        try:
            payload = f"data: {data}\n\n"
            await self._response.write(payload.encode())
        except (Exception, asyncio.CancelledError):
            self._closed = True

    async def recv(self) -> str:
        return ""

    async def close(self) -> None:
        self._closed = True


class HTTPTransport:
    """HTTP RPC transport — serves JSON-RPC 2.0 over HTTP with SSE streaming support."""

    def __init__(
        self,
        runtime: AgentRuntime | None = None,
        host: str = "127.0.0.1",
        port: int = 9090,
    ) -> None:
        self.runtime = runtime
        self.host = host
        self.port = port
        self._runner: aiohttp.web.AppRunner | None = None
        self._sse_tasks: dict[str, asyncio.Task[dict[str, Any] | None]] = {}

        from laffyhand.gateway.dispatcher import Dispatcher
        from laffyhand.gateway.handlers import register_all_handlers

        self._dispatcher = Dispatcher(runtime=runtime)
        register_all_handlers(self._dispatcher)

    def setup_routes(self, app: aiohttp.web.Application) -> None:
        """Attach RPC routes to an existing aiohttp Application."""
        app.router.add_post("/rpc", self._handle_rpc)
        app.router.add_get("/health", self._handle_health)
        app.router.add_options("/rpc", self._handle_cors_preflight)

    def _cancel_sse_task(self, conn_id: str) -> bool:
        """Cancel an active SSE task.

        When *conn_id* is ``"http"`` (the generic HTTP RPC conn_id), cancel
        *all* active SSE tasks — the frontend sends chat/cancel without a
        specific SSE stream identifier for HTTP transport.
        """
        if conn_id == "http":
            cancelled = False
            for cid in list(self._sse_tasks):
                task = self._sse_tasks[cid]
                if not task.done():
                    task.cancel()
                    cancelled = True
            return cancelled
        sse_task = self._sse_tasks.get(conn_id)
        if sse_task is not None and not sse_task.done():
            sse_task.cancel()
            return True
        return False

    async def start(self) -> None:
        import aiohttp.web

        app = aiohttp.web.Application()
        self.setup_routes(app)
        runner = aiohttp.web.AppRunner(app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, self.host, self.port)
        await site.start()
        self._runner = runner
        logger.info(f"HTTP transport listening on http://{self.host}:{self.port}/rpc")

    async def _handle_cors_preflight(
        self, request: aiohttp.web.Request
    ) -> aiohttp.web.StreamResponse:
        origin = _resolve_cors_origin(request.headers.get("Origin"))
        return _json_response({}, status=204, origin=origin)

    async def _handle_rpc(
        self, request: aiohttp.web.Request
    ) -> aiohttp.web.StreamResponse:
        body_bytes = await request.read()
        if len(body_bytes) > MAX_MESSAGE_SIZE:
            origin = _resolve_cors_origin(request.headers.get("Origin"))
            return _json_response(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": "Request too large"},
                    "id": None,
                },
                status=413,
                origin=origin,
            )
        body = body_bytes.decode("utf-8")
        if not body:
            origin = _resolve_cors_origin(request.headers.get("Origin"))
            return _json_response(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": "Parse error"},
                    "id": None,
                },
                status=400,
                origin=origin,
            )

        return await self._handle_rpc_inner(request, body)

    async def _handle_rpc_inner(
        self, request: aiohttp.web.Request, body: str
    ) -> aiohttp.web.StreamResponse:
        from laffyhand.gateway.protocol import from_json, Request

        origin = _resolve_cors_origin(request.headers.get("Origin"))

        try:
            message = from_json(body)
        except Exception:
            return _json_response(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": "Parse error"},
                    "id": None,
                },
                status=400,
                origin=origin,
            )

        if not isinstance(message, Request):
            return _json_response(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32600, "message": "Invalid request"},
                    "id": None,
                },
                status=400,
                origin=origin,
            )

        wants_sse = request.headers.get("Accept", "") == "text/event-stream"

        dispatcher = self._dispatcher
        entry = dispatcher.handlers.get(message.method)
        if entry is None:
            return _json_response(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {message.method}",
                    },
                    "id": message.id,
                },
                status=404,
                origin=origin,
            )

        if wants_sse and entry.streaming:
            return await self._handle_sse_stream(
                request, message, entry, dispatcher, origin
            )

        return await self._handle_rpc_call(message, entry, dispatcher, origin)

    async def _handle_sse_stream(
        self,
        request: aiohttp.web.Request,
        message: Request,
        entry: RegisteredHandler,
        dispatcher: Dispatcher,
        origin: str,
    ) -> aiohttp.web.StreamResponse:
        import aiohttp.web

        # Reject duplicate streaming for the same session
        params = message.params or {}
        session_id: str | None = params.get("session_id")
        if session_id is not None and dispatcher.get_active_session_stream(session_id) is not None:
            from laffyhand.gateway.protocol import Error, ErrorResponse

            return _json_response(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": SESSION_ALREADY_STREAMING,
                        "message": f"Session {session_id} already has an active stream",
                    },
                    "id": message.id,
                },
                status=409,
                origin=origin,
            )

        response = aiohttp.web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Accept",
            },
        )
        await response.prepare(request)
        conn_id = f"http_{id(response):x}"
        transport = _HTTPStreamTransport(response, conn_id, dispatcher=dispatcher)
        # Attach SSE task canceller so handle_chat_cancel can reach us
        transport.sse_canceller = self._cancel_sse_task

        runtime = self.runtime
        assert runtime is not None
        task: asyncio.Task[dict[str, Any] | None] = asyncio.create_task(
            entry.func(runtime, message.params or {}, transport, message.id, conn_id),
        )
        self._sse_tasks[conn_id] = task
        if session_id is not None:
            dispatcher.register_session_stream(session_id, task)

        def _cleanup(
            _t: asyncio.Task[Any],
            _sid: str | None = session_id,
            _cid: str = conn_id,
            _task: asyncio.Task[Any] = task,
        ) -> None:
            if self._sse_tasks.get(_cid) is _task:
                self._sse_tasks.pop(_cid, None)
            if _sid is not None:
                if dispatcher.get_active_session_stream(_sid) is _task:
                    dispatcher.unregister_session_stream(_sid)

        task.add_done_callback(_cleanup)

        try:
            await task
        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled (conn={conn_id})")
            try:
                from laffyhand.gateway.protocol import Notification

                done = Notification(
                    method="event",
                    params={"type": "finish", "data": "", "finish_reason": "cancelled"},
                )
                await transport.send(done.json())
            except Exception:
                logger.debug(
                    "Failed to send cancelled finish event (conn may be closed)"
                )
        except Exception:
            logger.exception(
                f"SSE stream error for method={message.method} (conn={conn_id})"
            )
            try:
                from laffyhand.gateway.protocol import ErrorResponse, Error

                await transport.send(
                    ErrorResponse(
                        id=message.id,
                        error=Error(code=-32603, message="Internal error"),
                    ).json()
                )
            except Exception:
                logger.warning(
                    "Failed to send SSE error event to client (connection may be closed)"
                )
        finally:
            try:
                await response.write_eof()
            except (ConnectionError, asyncio.CancelledError):
                pass
        return response

    async def _handle_rpc_call(
        self,
        message: Request,
        entry: RegisteredHandler,
        dispatcher: Dispatcher,
        origin: str,
    ) -> aiohttp.web.StreamResponse:
        try:
            from laffyhand.gateway.protocol import CHAT_CANCEL

            runtime = self.runtime
            assert runtime is not None
            if message.method == CHAT_CANCEL:
                # Attach SSE canceller + dispatcher so handle_chat_cancel can cancel by session
                cancel_transport = _NullTransport()
                cancel_transport.sse_canceller = self._cancel_sse_task
                cancel_transport.dispatcher = self._dispatcher
                result = await entry.func(
                    runtime,
                    message.params or {},
                    cancel_transport,
                    message.id,
                    "http",
                )
            else:
                result = await entry.func(
                    runtime,
                    message.params or {},
                    _NullTransport(),
                    message.id,
                    "http",
                )
            return _json_response(
                {"jsonrpc": "2.0", "id": message.id, "result": result},
                origin=origin,
            )
        except ValueError as e:
            logger.error(f"HTTP RPC validation error for method={message.method}: {e}")
            return _json_response(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32000, "message": str(e)},
                    "id": message.id,
                },
                origin=origin,
            )
        except Exception:
            logger.opt(exception=True).error(f"HTTP RPC error for method={message.method}")
            return _json_response(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": "Internal error"},
                    "id": message.id,
                },
                origin=origin,
            )

    async def _handle_health(
        self, request: aiohttp.web.Request
    ) -> aiohttp.web.StreamResponse:
        origin = _resolve_cors_origin(request.headers.get("Origin"))
        return _json_response({"status": "ok"}, origin=origin)

    async def close(self) -> None:
        # Cancel any in-flight SSE tasks
        for cid in list(self._sse_tasks):
            task = self._sse_tasks[cid]
            if not task.done():
                task.cancel()
        if self._runner:
            await self._runner.cleanup()
