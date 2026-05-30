from __future__ import annotations

import time
from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from laffyhand.gateway.protocol import (
    Request, Response, ErrorResponse, Error,
    METHOD_NOT_FOUND, INTERNAL_ERROR,
)

if TYPE_CHECKING:
    pass


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

    def register(
        self,
        method: str,
        handler: Handler,
        streaming: bool = False,
    ) -> None:
        self.handlers[method] = RegisteredHandler(func=handler, streaming=streaming)

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
        try:
            result = await entry.func(self.runtime, params, transport, request.id, conn_id)
        except Exception as e:
            logger.exception(f"Handler error for {request.method} (id={request.id}): {e}")
            error = Error(code=INTERNAL_ERROR, message=str(e))
            await transport.send(ErrorResponse(id=request.id, error=error).json())
            return
        elapsed = time.monotonic() - t0
        logger.debug(f"Handler {request.method} (id={request.id}) completed in {elapsed*1000:.1f}ms")

        if request.method == "shutdown":
            self.shutdown_requested = True

        if not entry.streaming:
            await transport.send(Response(id=request.id, result=result or {}).json())
