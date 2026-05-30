from __future__ import annotations

import argparse
import asyncio
import sys

from loguru import logger
from laffyhand import setup_logging
from laffyhand.config import LaffyConfig, load_config
from laffyhand.agent.schemas import (
    CompactionConfig,
    SessionUsage,
)
from laffyhand.agent.llm.builders import deepseek_route
from laffyhand.agent.llm.facade import LLM
from laffyhand.agent.session import SessionManager, TitleConfig
from laffyhand.agent.runtime import AgentRuntime
from laffyhand.agent.mcp import MCPService
from laffyhand.gateway.client import GatewayClient
from laffyhand.gateway.server import GatewayServer
from laffyhand.gateway.transport import InProcessTransport

SYSTEM_PROMPT = """
---
# Soul

You are a helpful assistant, your name is Laffybot. 
You can optionally use tools if needed. 
If no tools present, skip tool use.

---
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Laffyhand -- An AI Coding Agent")
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

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume the most recent active session if one exists",
    )
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Load a specific session by ID",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List recent sessions and exit",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to configuration file (default: ./laffyhand.yml)",
    )

    ui_parser = sub.add_parser("ui", help="Start the web UI")
    ui_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind")
    ui_parser.add_argument("--port", type=int, default=9090, help="Port to bind")
    ui_parser.add_argument("--no-open", action="store_true", help="Do not open browser")

    return parser.parse_args()


def print_sessions(sessions: list[dict]) -> None:
    if not sessions:
        print("No sessions.")
        return
    print(f"{'ID':<30} {'Status':<12} {'Title':<40} {'Messages':<8} {'Cost':<8}")
    print("-" * 100)
    for s in sessions:
        title = (s.get("title") or "(untitled)")[:40]
        cost = (s.get("input_tokens") or 0) + (s.get("output_tokens") or 0)
        cost_str = f"{cost // 1000}k" if cost > 1000 else str(cost)
        print(
            f"{s['id']:<30} {s['status']:<12} {title:<40} {s['message_count']:<8} {cost_str:<8}"
        )


async def create_runtime(config: LaffyConfig) -> AgentRuntime:
    route = deepseek_route(base_url=config.llm.base_url, api_key=config.llm.api_key)
    llm = LLM(model=config.llm.model_name, route=route)
    logger.info(f"Agent started, model={config.llm.model_name}")

    mcp_service = MCPService()
    if config.mcp.servers:
        await mcp_service.connect_all(config.mcp.servers)

    session_manager = SessionManager(config.db.path)
    compaction_config = CompactionConfig(
        tail_turns=config.agent.compaction_tail_turns,
    )

    runtime = AgentRuntime(
        llm=llm,
        session_manager=session_manager,
        mcp_service=mcp_service,
        compaction_config=compaction_config,
        title_config=TitleConfig(mode=config.agent.title_mode),  # type: ignore[arg-type]
        max_steps=config.agent.max_steps,
        max_subagents=config.agent.max_concurrent_subagents,
        db_path=config.db.path,
        context_size=config.llm.context_size,
    )

    skill_dirs = config.paths.skills if config.paths.skills else ["skills/"]
    runtime.load_skills(skill_dirs)

    runtime.load_agents(config.paths.agents)

    await runtime.init_tools(todo_path=config.paths.todos)
    return runtime


_stdin_reader: asyncio.StreamReader | None = None
_stdin_transport: asyncio.ReadTransport | None = None


async def async_input(prompt: str = "") -> str:
    global _stdin_reader, _stdin_transport
    if prompt:
        print(prompt, end="", flush=True)
    if _stdin_reader is None:
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        _stdin_transport, _ = await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        _stdin_reader = reader
    line = await _stdin_reader.readline()
    return line.decode(errors="replace").rstrip("\n")


async def _close_stdin_reader() -> None:
    global _stdin_reader, _stdin_transport
    if _stdin_transport is not None:
        _stdin_transport.close()
        _stdin_transport = None
    _stdin_reader = None


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
            open_browser=not args.no_open,
        )
        await runtime.shutdown()
        return

    runtime = await create_runtime(config)

    server_transport, client_transport = InProcessTransport.create_pair()
    gateway = GatewayServer(runtime, server_transport)
    gateway_task = asyncio.create_task(gateway.serve())

    client = GatewayClient(client_transport)
    await client.initialize()

    if args.list:
        sessions = await client.list_sessions(limit=20)
        print_sessions(sessions)
        await _shutdown_gateway(client, gateway_task)
        await _close_stdin_reader()
        return

    # Resolve or create session
    is_resumed = False
    if args.session:
        try:
            info = await client.load_session(args.session)
            logger.info(
                f"Loaded session {args.session} ({info.get('messages_count', 0)} messages)"
            )
            is_resumed = info.get("turn_count", 0) > 0
        except Exception:
            logger.error(f"Session not found: {args.session}")
            await _shutdown_gateway(client, gateway_task)
            await _close_stdin_reader()
            sys.exit(1)
    elif args.resume:
        sessions = await client.list_sessions(status="active", limit=1)
        if sessions:
            info = await client.load_session(sessions[0]["id"])
            logger.info(
                f"Resumed session {sessions[0]['id']} ({info.get('messages_count', 0)} messages)"
            )
            is_resumed = info.get("turn_count", 0) > 0
        else:
            session_id = await client.create_session(system_prompt=SYSTEM_PROMPT)
            logger.info(f"No active session to resume, starting new: {session_id}")
    else:
        session_id = await client.create_session(system_prompt=SYSTEM_PROMPT)
        logger.info(f"New session created: {session_id}")

    print(f"\nSession: {runtime.current_session_id}")
    if is_resumed:
        print("Resuming conversation")

    title_mode = config.agent.title_mode
    is_first_turn = not is_resumed

    try:
        while True:
            active = await client.list_active_subagents()
            if active:
                for sa in active:
                    print(
                        f"  ⚙  subagent [{sa['agent_type']}] {sa['task_id'][:8]} — {sa['status']}"
                    )

            try:
                user_prompt = await async_input("\nYou: ")
            except (EOFError, KeyboardInterrupt, asyncio.CancelledError):
                logger.info("Agent session ended")
                break

            if user_prompt.lower() in ("", "/exit", "quit", "exit"):
                logger.info("Agent session ended")
                break

            if user_prompt.startswith("/"):
                handled = await _handle_command(user_prompt, client)
                if handled:
                    continue
                cmd_name = user_prompt.split()[0]
                logger.warning(f"Unknown REPL command: {cmd_name}")
                print(f"Unknown command: {cmd_name}")
                continue

            async for event in client.chat_stream(user_prompt):
                if (
                    event.type == "content"
                    and event.finish_reason is not None
                    and event.usage
                ):
                    usage_info = await client.get_usage()
                    session_usage = SessionUsage(**usage_info["usage"])
                    print()
                    print(session_usage.display(event.usage))
                else:
                    print(event.data, end="")
            print()

            if is_first_turn and title_mode in ("on_create", "auto"):
                gen_title = await client.generate_session_title()
                if gen_title:
                    logger.info(f"Generated session title: {gen_title}")
            is_first_turn = False
    finally:
        await _shutdown_gateway(client, gateway_task)
        await runtime.shutdown()
        await _close_stdin_reader()


async def _shutdown_gateway(client: GatewayClient, gateway_task: asyncio.Task) -> None:
    try:
        await client.shutdown()
    except Exception:
        pass
    try:
        await gateway_task
    except (Exception, asyncio.CancelledError):
        pass


async def handle_repl_command(
    cmd: str,
    client: GatewayClient,
) -> bool:
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command == "/sessions":
        sessions = await client.list_sessions(limit=20)
        print_sessions(sessions)
        logger.info(f"Listed {len(sessions)} sessions")
        return True

    if command == "/session":
        if not arg:
            print("Usage: /session <id>")
            return True
        try:
            await client.load_session(arg)
            logger.info(f"Switched to session: {arg}")
            print(f"Switched to session: {arg}")
        except Exception:
            print(f"Session not found: {arg}")
        return True

    if command == "/new":
        session_id = await client.create_session(system_prompt=SYSTEM_PROMPT)
        logger.info(f"New session started: {session_id}")
        print(f"New session started: {session_id}")
        return True

    if command == "/title":
        if arg:
            await client.set_session_title(title=arg)
            logger.info(f"Title set to: {arg}")
            print(f"Title set to: {arg}")
        else:
            gen_title = await client.generate_session_title()
            if gen_title:
                print(f"Generated title: {gen_title}")
            else:
                print("Could not generate title.")
        return True

    if command == "/fork":
        try:
            child_id = await client.fork_session()
            logger.info(f"Forked to new session: {child_id}")
            print(f"Forked to new session: {child_id}")
        except Exception:
            print("No active session to fork.")
        return True

    if command == "/archive":
        target = arg
        await client.archive_session(session_id=target)
        logger.info(f"Archived session: {target or '(current)'}")
        print(f"Archived session: {target or '(current)'}")
        return True

    if command == "/search":
        if not arg:
            print("Usage: /search <query>")
            print("  Search session messages. Supports FTS5 syntax if available")
            print("  (quotes for phrase, AND/OR, prefix*, etc.)")
            return True
        sessions = await client.search_sessions(arg, limit=20)
        if not sessions:
            print(f"No sessions found for query: {arg}")
        else:
            print(f"Found {len(sessions)} session(s) for query: {arg}")
            print_sessions(sessions)
        logger.info(f"Searched for '{arg}', found {len(sessions)} session(s)")
        return True

    return False


_handle_command = handle_repl_command


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
