from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from collections.abc import Callable
from typing import Any, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from aiohttp.web import Application, Request, Response, StreamResponse
    from laffyhand.agent.runtime import AgentRuntime


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


def _get_ui_dir() -> str:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        return os.path.join(meipass, "ui")
    return str(Path(__file__).resolve().parent / "ui" / "dist")


async def _fallback_handler(request: Request) -> Response:
    import aiohttp.web

    return aiohttp.web.Response(
        text="<h1>UI not built</h1><p>Run <code>cd laffyhand/ui && npm run build</code></p>",
        content_type="text/html",
        headers=_SECURITY_HEADERS,
    )


def _add_security_middleware(app: Application) -> None:
    import aiohttp.web

    @aiohttp.web.middleware
    async def _middleware(request: Request, handler: Callable[..., Any]) -> Response:
        response: Response = await handler(request)
        for key, value in _SECURITY_HEADERS.items():
            response.headers[key] = value
        return response

    app.middlewares.append(_middleware)


async def run_ui_server(
    runtime: AgentRuntime,
    host: str = "127.0.0.1",
    port: int = 9090,
) -> None:
    import aiohttp.web

    from laffyhand.gateway.http_transport import HTTPTransport

    ui_dir = _get_ui_dir()

    transport = HTTPTransport(runtime=runtime)
    app = aiohttp.web.Application()
    transport.setup_routes(app)
    _add_security_middleware(app)

    if os.path.isdir(ui_dir):

        async def _serve_index(request: Request) -> StreamResponse:
            import aiohttp.web

            return aiohttp.web.FileResponse(os.path.join(ui_dir, "index.html"))

        async def _spa_fallback(request: Request) -> StreamResponse:
            import aiohttp.web

            # Don't intercept RPC or health endpoints
            if request.path.startswith(("/rpc", "/health")):
                raise aiohttp.web.HTTPNotFound()
            return aiohttp.web.FileResponse(os.path.join(ui_dir, "index.html"))

        # Static assets under /assets/
        app.router.add_static(
            "/assets", os.path.join(ui_dir, "assets"), show_index=False
        )
        # Root serves index.html
        app.router.add_get("/", _serve_index)
        # SPA fallback: anything else serves index.html (for client-side routing)
        app.router.add_get("/{tail:.*}", _spa_fallback)
        logger.info(f"Serving UI static files from {ui_dir}")
    else:
        logger.warning(f"UI dist directory not found at {ui_dir}")
        app.router.add_get("/", _fallback_handler)

    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, host, port)
    await site.start()

    url = f"http://{host}:{port}"
    logger.info(f"Laffyhand UI running at {url} — open this URL in your browser")

    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()
