from __future__ import annotations

import asyncio
import os
import sys
import webbrowser
from pathlib import Path

from loguru import logger


def _get_ui_dir() -> str:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        return os.path.join(meipass, "ui")
    return str(Path(__file__).resolve().parent / "ui" / "dist")


async def _fallback_handler(request: object) -> object:
    import aiohttp.web
    return aiohttp.web.Response(
        text="<h1>UI not built</h1><p>Run <code>cd laffyhand/ui && npm run build</code></p>",
        content_type="text/html",
    )


async def run_ui_server(
    runtime: object,
    host: str = "127.0.0.1",
    port: int = 9090,
    open_browser: bool = True,
) -> None:
    import aiohttp.web

    from laffyhand.gateway.http_transport import HTTPTransport

    ui_dir = _get_ui_dir()

    app = aiohttp.web.Application()

    transport = HTTPTransport(runtime=runtime)
    app.router.add_post("/rpc", transport._handle_rpc)
    app.router.add_get("/health", transport._handle_health)

    if os.path.isdir(ui_dir):
        app.router.add_static("/", ui_dir, show_index=True)
        logger.info(f"Serving UI static files from {ui_dir}")
    else:
        logger.warning(f"UI dist directory not found at {ui_dir}")
        app.router.add_get("/", _fallback_handler)  # type: ignore[arg-type]

    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, host, port)
    await site.start()

    url = f"http://{host}:{port}"
    logger.info(f"Laffyhand UI running on {url}")

    if open_browser:
        webbrowser.open(url)

    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()
