from __future__ import annotations

import argparse
import asyncio
import sys

from loguru import logger
from laffyhand import setup_logging
from laffyhand.config import LaffyConfig, load_config
from laffyhand.agent.runtime import AgentRuntime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Laffyhand -- An AI Coding Agent")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to configuration file (default: ./laffyhand.yml)",
    )
    sub = parser.add_subparsers(dest="command")

    gateway_parser = sub.add_parser("gateway", help="Gateway server commands")
    gateway_sub = gateway_parser.add_subparsers(dest="gateway_command")
    serve_parser = gateway_sub.add_parser("serve", help="Start the gateway server")
    serve_parser.add_argument(
        "--listen",
        type=str,
        default="stdio://",
        help="Transport to listen on: stdio://, ws://HOST:PORT, http://HOST:PORT",
    )
    serve_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind (for ws/http transports)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=9090,
        help="Port to bind (for ws/http transports)",
    )

    ui_parser = sub.add_parser("ui", help="Start the web UI")
    ui_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind")
    ui_parser.add_argument("--port", type=int, default=9090, help="Port to bind")

    return parser.parse_args()


async def create_runtime(config: LaffyConfig) -> AgentRuntime:
    runtime = AgentRuntime(config=config)

    if config.mcp.servers:
        await runtime.mcp_service.connect_all(config.mcp.servers)

    skill_dirs = config.paths.skills if config.paths.skills else ["skills/"]
    runtime.load_skills(skill_dirs)
    runtime.load_agents(config.paths.agents)
    await runtime.init_tools()
    return runtime


async def _run_gateway_serve(args: argparse.Namespace, config: LaffyConfig) -> None:
    from laffyhand.gateway import GatewayServer, StdioTransport

    runtime = await create_runtime(config)
    listen = args.listen

    if listen.startswith("ws://"):
        host = args.host
        port = args.port
        from laffyhand.gateway.http_transport import WSTransport

        ws_mgr = WSTransport(runtime=runtime, host=host, port=port)
        await ws_mgr.start()
        logger.info(f"WebSocket gateway running on ws://{host}:{port}/ws")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
    elif listen.startswith("http://"):
        host = args.host
        port = args.port
        from laffyhand.gateway.http_transport import HTTPTransport

        http_mgr = HTTPTransport(runtime=runtime, host=host, port=port)
        await http_mgr.start()
        logger.info(f"HTTP gateway running on http://{host}:{port}/rpc")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
    else:
        transport = StdioTransport()
        gateway = GatewayServer(runtime, transport)
        await gateway.serve()


async def main():
    args = parse_args()
    config = load_config(args.config)
    setup_logging(
        log_dir=config.logging.dir,
        level=config.logging.level,
        retention=config.logging.retention_days,
        console=config.logging.console,
    )

    if args.command == "gateway":
        if args.gateway_command == "serve":
            await _run_gateway_serve(args, config)
        else:
            print("Usage: laffyhand gateway serve [--listen ...]")
        return

    if args.command == "ui":
        runtime = await create_runtime(config)
        from laffyhand.ui_server import run_ui_server

        await run_ui_server(
            runtime,
            host=args.host,
            port=args.port,
        )
        await runtime.shutdown()
        return

    parser = argparse.ArgumentParser(description="Laffyhand -- An AI Coding Agent")
    parser.print_help()


def entry_point() -> None:
    try:
        asyncio.run(main())
    except Exception:
        logger.exception("Unhandled exception")
        print(
            "\nError: Laffyhand encountered an unexpected error. Check logs/ for details.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    entry_point()
