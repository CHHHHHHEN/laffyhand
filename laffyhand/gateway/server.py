from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from laffyhand.gateway.dispatcher import Dispatcher
from laffyhand.gateway.handlers import register_all_handlers
from laffyhand.gateway.protocol import from_json, Request, ErrorResponse, Error, PARSE_ERROR

if TYPE_CHECKING:
    from laffyhand.agent.runtime import AgentRuntime
    from laffyhand.gateway.transport import Transport


class GatewayServer:
    def __init__(self, runtime: AgentRuntime, transport: Transport) -> None:
        self.runtime = runtime
        self.transport = transport
        self.dispatcher = Dispatcher(runtime=runtime)
        self._running = False
        self._handlers_registered = False

    def _ensure_handlers(self) -> None:
        if self._handlers_registered:
            return
        register_all_handlers(self.dispatcher)
        self._handlers_registered = True

    async def serve(self) -> None:
        self._ensure_handlers()
        self._running = True
        transport = self.transport
        conn_id = transport.connection_id
        logger.info(f"Gateway serving on {type(transport).__name__} ({conn_id})")

        try:
            while self._running:
                raw = await transport.recv()
                if not raw:
                    logger.info("Gateway transport closed")
                    break

                try:
                    message = from_json(raw)
                except Exception as e:
                    logger.warning(f"Failed to parse message: {e}")
                    err = Error(code=PARSE_ERROR, message=f"Parse error: {e}")
                    await transport.send(ErrorResponse(id=None, error=err).json())
                    continue

                if not isinstance(message, Request):
                    logger.warning(f"Unexpected message type: {type(message).__name__}")
                    continue

                await self.dispatcher.dispatch(message, transport, conn_id)
                if self.dispatcher.shutdown_requested:
                    logger.info("Shutdown requested, stopping serve loop")
                    break
        except Exception as e:
            logger.error(f"Gateway serve error: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        self._running = False
        try:
            await self.transport.close()
        except Exception:
            pass
        logger.info("Gateway shutdown complete")

    def stop(self) -> None:
        self._running = False
