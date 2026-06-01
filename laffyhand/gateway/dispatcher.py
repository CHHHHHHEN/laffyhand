from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from collections.abc import Callable, Coroutine
from typing import Any

from loguru import logger

from laffyhand.agent.runtime import AgentRuntime
from laffyhand.gateway.protocol import (
    Request,
    Response,
    ErrorResponse,
    Error,
    METHOD_NOT_FOUND,
    INTERNAL_ERROR,
    SHUTDOWN,
)
from laffyhand.gateway.transport import Transport


Handler = Callable[
    [AgentRuntime, dict[str, Any], Transport, str | int | None, str],
    Coroutine[Any, Any, dict[str, Any] | None],
]


@dataclass
class RegisteredHandler:
    func: Handler
    streaming: bool = False


@dataclass
class Dispatcher:
    runtime: AgentRuntime | None = None
    handlers: dict[str, RegisteredHandler] = field(default_factory=dict)
    shutdown_requested: bool = False
    _active_tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)

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
        transport: Transport,
        conn_id: str,
    ) -> None:
        entry = self.handlers.get(request.method)
        if entry is None:
            logger.warning(f"Method not found: {request.method} (id={request.id})")
            error = Error(
                code=METHOD_NOT_FOUND, message=f"Method not found: {request.method}"
            )
            await transport.send(ErrorResponse(id=request.id, error=error).json())
            return

        params = request.params or {}
        t0 = time.monotonic()

        if entry.streaming and request.method != SHUTDOWN:
            task = asyncio.create_task(
                self._run_streaming(entry, params, transport, request.id, conn_id),
            )
            self._active_tasks[conn_id] = task

            def _cleanup(
                _t: asyncio.Task[None], _cid: str = conn_id, _task: asyncio.Task[None] = task
            ) -> None:
                if self._active_tasks.get(_cid) is _task:
                    self._active_tasks.pop(_cid, None)

            task.add_done_callback(_cleanup)
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.debug(
                f"Handler {request.method} (id={request.id}) started in {elapsed_ms:.1f}ms"
            )
            return

        runtime = self.runtime
        assert runtime is not None
        try:
            result = await entry.func(
                runtime, params, transport, request.id, conn_id
            )
        except Exception:
            logger.exception(f"Handler error for {request.method} (id={request.id})")
            error = Error(code=INTERNAL_ERROR, message="Internal error")
            await transport.send(ErrorResponse(id=request.id, error=error).json())
            if request.method == SHUTDOWN:
                self.shutdown_requested = True
            return
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.debug(
            f"Handler {request.method} (id={request.id}) completed in {elapsed_ms:.1f}ms"
        )

        if request.method == SHUTDOWN:
            self.shutdown_requested = True

        if not entry.streaming:
            await transport.send(Response(id=request.id, result=result or {}).json())

    async def _run_streaming(
        self,
        entry: RegisteredHandler,
        params: dict[str, Any],
        transport: Transport,
        request_id: str | int | None,
        conn_id: str,
    ) -> None:
        runtime = self.runtime
        assert runtime is not None
        try:
            await entry.func(runtime, params, transport, request_id, conn_id)
        except asyncio.CancelledError:
            logger.info(f"Streaming handler cancelled (conn={conn_id})")
            raise
        except Exception:
            logger.exception(f"Streaming handler error (conn={conn_id})")
