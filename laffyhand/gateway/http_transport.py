from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from laffyhand.gateway.protocol import MAX_MESSAGE_SIZE
from laffyhand.gateway.transport import Transport, _NullTransport


# Default CORS origin for Vite dev server (port 1420).
# Production: UI served from the same host:port -> same-origin -> CORS irrelevant.
ALLOWED_CORS_ORIGINS = frozenset({
    "http://localhost:1420",
    "http://127.0.0.1:1420",
})
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


def _json_response(data: dict[str, Any], status: int = 200, origin: str = _DEFAULT_CORS_ORIGIN) -> Any:
    import aiohttp.web
    return aiohttp.web.json_response(data, status=status, headers=_cors_headers(origin))


class _WSConnection(Transport):
    def __init__(self, ws: Any, conn_id: str) -> None:
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
                return msg.data
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
        runtime: Any = None,
        host: str = "127.0.0.1",
        port: int = 9090,
    ) -> None:
        self.runtime = runtime
        self.host = host
        self.port = port
        self._runner: Any = None
        self._gateway_servers: list[Any] = []

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

    async def _handle_ws(self, request: Any) -> Any:
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

    async def _handle_health(self, request: Any) -> Any:
        origin = _resolve_cors_origin(request.headers.get("Origin"))
        return _json_response({"status": "ok"}, origin=origin)

    async def close(self) -> None:
        for g in list(self._gateway_servers):
            g.stop()
        if self._runner:
            await self._runner.cleanup()


class _HTTPStreamTransport(Transport):
    """Transport wrapping an SSE StreamResponse — used per streaming request."""

    def __init__(self, response: Any, conn_id: str, dispatcher: Any = None) -> None:
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
        runtime: Any = None,
        host: str = "127.0.0.1",
        port: int = 9090,
    ) -> None:
        self.runtime = runtime
        self.host = host
        self.port = port
        self._runner: Any = None
        self._sse_tasks: dict[str, asyncio.Task] = {}

        from laffyhand.gateway.dispatcher import Dispatcher
        from laffyhand.gateway.handlers import register_all_handlers

        self._dispatcher = Dispatcher(runtime=runtime)
        register_all_handlers(self._dispatcher)

    def setup_routes(self, app: Any) -> None:
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

    async def _handle_cors_preflight(self, request: Any) -> Any:
        origin = _resolve_cors_origin(request.headers.get("Origin"))
        return _json_response({}, status=204, origin=origin)

    async def _handle_rpc(self, request: Any) -> Any:
        body_bytes = await request.read()
        if len(body_bytes) > MAX_MESSAGE_SIZE:
            origin = _resolve_cors_origin(request.headers.get("Origin"))
            return _json_response(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Request too large"}, "id": None},
                status=413,
                origin=origin,
            )
        body = body_bytes.decode("utf-8")
        if not body:
            origin = _resolve_cors_origin(request.headers.get("Origin"))
            return _json_response(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None},
                status=400,
                origin=origin,
            )

        return await self._handle_rpc_inner(request, body)

    async def _handle_rpc_inner(self, request: Any, body: str) -> Any:
        from laffyhand.gateway.protocol import from_json, Request

        origin = _resolve_cors_origin(request.headers.get("Origin"))

        try:
            message = from_json(body)
        except Exception:
            return _json_response(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None},
                status=400,
                origin=origin,
            )

        if not isinstance(message, Request):
            return _json_response(
                {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid request"}, "id": None},
                status=400,
                origin=origin,
            )

        wants_sse = request.headers.get("Accept", "") == "text/event-stream"

        dispatcher = self._dispatcher
        entry = dispatcher.handlers.get(message.method)
        if entry is None:
            return _json_response(
                {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Method not found: {message.method}"}, "id": message.id},
                status=404,
                origin=origin,
            )

        if wants_sse and entry.streaming:
            return await self._handle_sse_stream(request, message, entry, dispatcher, origin)

        return await self._handle_rpc_call(message, entry, dispatcher, origin)

    async def _handle_sse_stream(
        self, request: Any, message: Any, entry: Any, dispatcher: Any, origin: str,
    ) -> Any:
        import aiohttp.web

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
        transport._sse_canceller = self._cancel_sse_task  # type: ignore[attr-defined]

        task = asyncio.create_task(
            entry.func(self.runtime, message.params or {}, transport, message.id, conn_id),
        )
        self._sse_tasks[conn_id] = task
        task.add_done_callback(lambda _: self._sse_tasks.pop(conn_id, None) if self._sse_tasks.get(conn_id) is task else None)

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
                logger.debug("Failed to send cancelled finish event (conn may be closed)")
        except Exception:
            logger.exception(f"SSE stream error for method={message.method} (conn={conn_id})")
            try:
                from laffyhand.gateway.protocol import ErrorResponse, Error
                await transport.send(ErrorResponse(id=message.id, error=Error(code=-32603, message="Internal error")).json())
            except Exception:
                logger.warning("Failed to send SSE error event to client (connection may be closed)")
        finally:
            try:
                await response.write_eof()
            except (ConnectionError, asyncio.CancelledError):
                pass
        return response

    async def _handle_rpc_call(
        self, message: Any, entry: Any, dispatcher: Any, origin: str,
    ) -> Any:
        try:
            from laffyhand.gateway.protocol import CHAT_CANCEL

            if message.method == CHAT_CANCEL:
                # Attach SSE canceller so handle_chat_cancel can cancel active SSE tasks
                cancel_transport = _NullTransport()
                cancel_transport._sse_canceller = self._cancel_sse_task  # type: ignore[attr-defined]
                result = await entry.func(self.runtime, message.params or {}, cancel_transport, message.id, "http")
            else:
                result = await entry.func(self.runtime, message.params or {}, _NullTransport(), message.id, "http")
            return _json_response(
                {"jsonrpc": "2.0", "id": message.id, "result": result},
                origin=origin,
            )
        except Exception:
            logger.error(f"HTTP RPC error for method={message.method}")
            return _json_response(
                {"jsonrpc": "2.0", "error": {"code": -32603, "message": "Internal error"}, "id": message.id},
                status=500,
                origin=origin,
            )

    async def _handle_health(self, request: Any) -> Any:
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
