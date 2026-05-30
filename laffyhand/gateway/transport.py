from __future__ import annotations

import sys
import asyncio
from abc import ABC, abstractmethod
from asyncio import Queue, StreamReader
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    pass


class Transport(ABC):
    connection_id: str = ""

    @abstractmethod
    async def send(self, data: str) -> None: ...

    @abstractmethod
    async def recv(self) -> str: ...

    @abstractmethod
    async def close(self) -> None: ...


class StdioTransport(Transport):
    def __init__(self, reader: StreamReader | None = None) -> None:
        self.connection_id = "stdio"
        self._reader: StreamReader | None = reader
        self._writer = sys.stdout
        self._closed = False

    async def send(self, data: str) -> None:
        if self._closed:
            return
        self._writer.write(data + "\n")
        self._writer.flush()

    async def recv(self) -> str:
        if self._reader is None:
            loop = asyncio.get_running_loop()
            reader = StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            await loop.connect_read_pipe(lambda: protocol, sys.stdin)
            self._reader = reader
        line = await self._reader.readline()
        return line.decode().rstrip("\n")

    async def close(self) -> None:
        self._closed = True


class InProcessTransport(Transport):
    connection_id: str = "inprocess"

    def __init__(self) -> None:
        self._client_queue: Queue[str] = Queue()
        self._server_queue: Queue[str] = Queue()
        self._closed = False

    async def send(self, data: str) -> None:
        if self._closed:
            return
        await self._client_queue.put(data)

    async def recv(self) -> str:
        if self._closed:
            return ""
        return await self._server_queue.get()

    async def close(self) -> None:
        self._closed = True


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
        except Exception as e:
            logger.debug(f"WebSocket send error ({self.connection_id}): {e}")
            self._closed = True

    async def recv(self) -> str:
        if self._closed:
            return ""
        try:
            msg = await self._ws.receive()
            if msg.type == self._WSMsgType.TEXT:
                return msg.data
            if msg.type in (self._WSMsgType.BINARY, self._WSMsgType.CLOSE, self._WSMsgType.PING, self._WSMsgType.PONG):
                self._closed = True
                return ""
            return ""
        except Exception as e:
            logger.debug(f"WebSocket recv error ({self.connection_id}): {e}")
            self._closed = True
            return ""

    async def close(self) -> None:
        self._closed = True
        try:
            await self._ws.close()
        except Exception as e:
            logger.debug(f"WebSocket close error ({self.connection_id}): {e}")


class WSTransport:
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

        logger.info(f"WebSocket client connected: {conn_id}")
        await gateway.serve()
        logger.info(f"WebSocket client disconnected: {conn_id}")
        return ws

    async def _handle_health(self, request: Any) -> Any:
        import aiohttp.web
        return aiohttp.web.json_response({"status": "ok"})

    async def close(self) -> None:
        for g in self._gateway_servers:
            g.stop()
        if self._runner:
            await self._runner.cleanup()


class HTTPTransport:
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

    async def start(self) -> None:
        import aiohttp.web
        app = aiohttp.web.Application()
        app.router.add_post("/rpc", self._handle_rpc)
        app.router.add_get("/health", self._handle_health)
        runner = aiohttp.web.AppRunner(app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, self.host, self.port)
        await site.start()
        self._runner = runner
        logger.info(f"HTTP transport listening on http://{self.host}:{self.port}/rpc")

    async def _handle_rpc(self, request: Any) -> Any:
        import aiohttp.web
        body = await request.text()
        if not body:
            return aiohttp.web.json_response(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None},
                status=400,
            )

        from laffyhand.gateway.protocol import from_json, Request, Response as RpcResponse, ErrorResponse, Error
        try:
            message = from_json(body)
        except Exception as e:
            return aiohttp.web.json_response(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": f"Parse error: {e}"}, "id": None},
                status=400,
            )

        if not isinstance(message, Request):
            return aiohttp.web.json_response(
                {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid request"}, "id": None},
                status=400,
            )

        wants_sse = request.headers.get("Accept", "") == "text/event-stream"

        from laffyhand.gateway.dispatcher import Dispatcher
        from laffyhand.gateway.handlers import register_all_handlers

        dispatcher = Dispatcher(runtime=self.runtime)
        register_all_handlers(dispatcher)

        entry = dispatcher.handlers.get(message.method)
        if entry is None:
            return aiohttp.web.json_response(
                {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Method not found: {message.method}"}, "id": message.id},
                status=404,
            )

        if wants_sse and entry.streaming:
            response = aiohttp.web.StreamResponse(
                status=200,
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                },
            )
            await response.prepare(request)
            transport = _HTTPStreamTransport(response, f"http_{id(response):x}")
            try:
                await entry.func(self.runtime, message.params or {}, transport, message.id, transport.connection_id)
                await transport.send(RpcResponse(id=message.id, result={"status": "completed"}).json())
            except Exception as e:
                logger.exception(f"SSE stream error: {e}")
                await transport.send(ErrorResponse(id=message.id, error=Error(code=-32603, message=str(e))).json())
            await response.write_eof()
            return response

        try:
            result = await entry.func(self.runtime, message.params or {}, _NullTransport(), message.id, "http")
            return aiohttp.web.json_response(
                {"jsonrpc": "2.0", "id": message.id, "result": result},
            )
        except Exception as e:
            logger.exception(f"HTTP RPC error: {e}")
            return aiohttp.web.json_response(
                {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": message.id},
                status=500,
            )

    async def _handle_health(self, request: Any) -> Any:
        import aiohttp.web
        return aiohttp.web.json_response({"status": "ok"})

    async def close(self) -> None:
        if self._runner:
            await self._runner.cleanup()


class _HTTPStreamTransport(Transport):
    def __init__(self, response: Any, conn_id: str) -> None:
        self._response = response
        self.connection_id = conn_id
        self._closed = False

    async def send(self, data: str) -> None:
        if self._closed:
            return
        try:
            payload = f"data: {data}\n\n"
            await self._response.write(payload.encode())
        except Exception:
            self._closed = True

    async def recv(self) -> str:
        return ""

    async def close(self) -> None:
        self._closed = True


class _NullTransport(Transport):
    connection_id: str = "null"

    async def send(self, data: str) -> None:
        pass

    async def recv(self) -> str:
        return ""

    async def close(self) -> None:
        pass
