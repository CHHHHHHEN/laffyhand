from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from laffyhand.gateway.protocol import (
    Request, Response, ErrorResponse, Error,
    METHOD_NOT_FOUND, INTERNAL_ERROR, SHUTDOWN,
)


Handler = Callable[
    [Any, dict[str, Any], Any, str | int | None, str],
    Awaitable[dict[str, Any] | None],
]


@dataclass
class RegisteredHandler:
    func: Handler
    streaming: bool = False


@dataclass
class Dispatcher:
    runtime: Any = None
    handlers: dict[str, RegisteredHandler] = field(default_factory=dict)
    shutdown_requested: bool = False
    _active_tasks: dict[str, asyncio.Task] = field(default_factory=dict)

    def register(
        self,
        method: str,
        handler: Handler,
        streaming: bool = False,
    ) -> None:
        self.handlers[method] = RegisteredHandler(func=handler, streaming=streaming)

    def cancel_connection(self, conn_id: str) -> bool:
        task = self._active_tasks.get(conn_id)
        if task is not None and not task.done():
            task.cancel()
            return True
        return False

    async def dispatch(
        self,
        request: Request,
        transport: Any,
        conn_id: str,
    ) -> None:
        entry = self.handlers.get(request.method)
        if entry is None:
            logger.warning(f"Method not found: {request.method} (id={request.id})")
            error = Error(code=METHOD_NOT_FOUND, message=f"Method not found: {request.method}")
            await transport.send(ErrorResponse(id=request.id, error=error).json())
            return

        params = request.params or {}
        t0 = time.monotonic()

        if entry.streaming and request.method != SHUTDOWN:
            task = asyncio.create_task(
                self._run_streaming(entry, params, transport, request.id, conn_id),
            )
            self._active_tasks[conn_id] = task
            task.add_done_callback(lambda _: self._active_tasks.pop(conn_id, None))
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.debug(f"Handler {request.method} (id={request.id}) started in {elapsed_ms:.1f}ms")
            return

        try:
            result = await entry.func(self.runtime, params, transport, request.id, conn_id)
        except Exception:
            logger.exception(f"Handler error for {request.method} (id={request.id})")
            error = Error(code=INTERNAL_ERROR, message="Internal error")
            await transport.send(ErrorResponse(id=request.id, error=error).json())
            return
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.debug(f"Handler {request.method} (id={request.id}) completed in {elapsed_ms:.1f}ms")

        if request.method == SHUTDOWN:
            self.shutdown_requested = True

        if not entry.streaming:
            await transport.send(Response(id=request.id, result=result or {}).json())

    async def _run_streaming(
        self,
        entry: RegisteredHandler,
        params: dict[str, Any],
        transport: Any,
        request_id: str | int | None,
        conn_id: str,
    ) -> None:
        try:
            await entry.func(self.runtime, params, transport, request_id, conn_id)
        except asyncio.CancelledError:
            logger.info(f"Streaming handler cancelled (conn={conn_id})")
        except Exception:
            logger.exception(f"Streaming handler error (conn={conn_id})")
