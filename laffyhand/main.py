from __future__ import annotations

import argparse
import asyncio
import os
import sys

from loguru import logger
from laffyhand import setup_logging
from laffyhand.config import LaffyConfig, load_config
from laffyhand.agent.schemas import (
    AgentState,
    CompactionConfig,
    SystemMessage,
    UserMessage,
    SessionUsage,
)
from laffyhand.agent.llm.builders import deepseek_route
from laffyhand.agent.llm.facade import LLM
from laffyhand.agent.session import SessionManager, TitleConfig
from laffyhand.agent.runtime import AgentRuntime
from laffyhand.agent.mcp import MCPService

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
    return parser.parse_args()


def print_sessions(sessions, session_manager: SessionManager | None = None) -> None:
    if not sessions:
        print("No sessions.")
        return
    print(f"{'ID':<30} {'Status':<12} {'Title':<40} {'Messages':<8} {'Cost':<8}")
    print("-" * 100)
    for s in sessions:
        title = (s.title or "(untitled)")[:40]
        cost = s.input_tokens + s.output_tokens
        cost_str = f"{cost // 1000}k" if cost > 1000 else str(cost)
        print(
            f"{s.id:<30} {s.status:<12} {title:<40} {s.message_count:<8} {cost_str:<8}"
        )


async def resolve_session(
    args: argparse.Namespace,
    session_manager: SessionManager,
    system_message: SystemMessage,
    config: LaffyConfig,
) -> AgentState | None:
    context_size = config.llm.context_size
    if args.session:
        loaded = session_manager.resolve(
            args.session,
            system_message,
            context_size,
        )
        if loaded is not None:
            logger.info(
                f"Loaded session {args.session} ({len(loaded.messages)} messages)"
            )
            return loaded
        logger.error(f"Session not found: {args.session}")
        sys.exit(1)

    if args.resume:
        last_active = session_manager.get_active()
        if last_active is not None:
            loaded = session_manager.resolve(
                last_active.id,
                system_message,
                context_size,
            )
            if loaded is not None:
                logger.info(
                    f"Resumed session {loaded.session_id} ({len(loaded.messages)} messages)"
                )
                return loaded
        logger.info("No active session to resume, starting new")

    session = session_manager.create(cwd=os.getcwd(), model=config.llm.model_name)
    logger.info(f"New session created: {session.id}")
    return AgentState(
        messages=[system_message],
        session_id=session.id,
        usage=SessionUsage(context_size=context_size),
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
    return line.decode().rstrip("\n")


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

    runtime = await create_runtime(config)

    if args.list:
        sessions = runtime.session_manager.list_sessions(limit=20)
        print_sessions(sessions)
        await runtime.shutdown()
        await _close_stdin_reader()
        return

    system_content = runtime.build_system_prompt(SYSTEM_PROMPT)
    system_message = SystemMessage(content=system_content)

    state = await resolve_session(args, runtime.session_manager, system_message, config)
    if state is None:
        await runtime.shutdown()
        await _close_stdin_reader()
        return
    runtime.state = state

    print(f"\nSession: {runtime.state.session_id}")
    if runtime.state.turn_count > 0:
        print(f"Resuming conversation ({runtime.state.turn_count} previous turns)")

    try:
        while True:
            if (
                runtime.state
                and runtime.subagent_manager.active_count(runtime.state.session_id) > 0
            ):
                active = runtime.subagent_manager.list_active(runtime.state.session_id)
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
                handled = await _handle_command(user_prompt, runtime)
                if handled:
                    continue
                cmd_name = user_prompt.split()[0]
                logger.warning(f"Unknown REPL command: {cmd_name}")
                print(f"Unknown command: {cmd_name}")
                continue

            if runtime.state is None:
                continue

            runtime.state.step = 0
            user_message = UserMessage(content=user_prompt)
            runtime.state.messages.append(user_message)

            if runtime.state.session_id:
                runtime.session_manager.append_messages(
                    runtime.state.session_id, runtime.state.messages
                )

            if runtime.state.turn_count == 0 and runtime.title_config.mode in (
                "on_create",
                "auto",
            ):
                gen_title = await runtime.generate_title_for_current()
                if gen_title:
                    logger.info(f"Generated session title: {gen_title}")

            async for event in runtime.run_agent_turn():
                if (
                    event.type == "content"
                    and event.finish_reason is not None
                    and event.usage
                ):
                    print()
                    print(runtime.state.usage.display(event.usage))
                else:
                    print(event.data, end="")
            print()
    finally:
        await runtime.shutdown()
        await _close_stdin_reader()


async def handle_repl_command(
    cmd: str,
    runtime: AgentRuntime,
) -> bool:
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command == "/sessions":
        sessions = runtime.session_manager.list_sessions(limit=20)
        print_sessions(sessions, runtime.session_manager)
        logger.info(f"Listed {len(sessions)} sessions")
        return True

    if command == "/session":
        if not arg:
            print("Usage: /session <id>")
            return True
        if runtime.switch_session(arg):
            logger.info(f"Switched to session: {arg}")
            print(f"Switched to session: {arg}")
        else:
            print(f"Session not found: {arg}")
        return True

    if command == "/new":
        system_prompt = SystemMessage(
            content=runtime.build_system_prompt(SYSTEM_PROMPT)
        )
        runtime.new_session(system_prompt)
        assert runtime.state is not None
        logger.info(f"New session started: {runtime.state.session_id}")
        print(f"New session started: {runtime.state.session_id}")
        return True

    if command == "/title":
        if arg:
            if runtime.state and runtime.state.session_id:
                runtime.session_manager.set_title(runtime.state.session_id, arg)
                logger.info(f"Title set for {runtime.state.session_id}: {arg}")
                print(f"Title set to: {arg}")
            else:
                print("No active session.")
        elif runtime.state and runtime.state.session_id:
            gen_title = await runtime.generate_title_for_current()
            if gen_title:
                print(f"Generated title: {gen_title}")
            else:
                print("Could not generate title.")
        return True

    if command == "/fork":
        child_id = runtime.fork_session()
        if child_id:
            logger.info(f"Forked to new session: {child_id}")
            print(f"Forked to new session: {child_id}")
        else:
            print("No active session to fork.")
        return True

    if command == "/archive":
        target = arg or (runtime.state.session_id if runtime.state else "")
        if target:
            runtime.session_manager.archive(target)
            logger.info(f"Archived session: {target}")
            print(f"Archived session: {target}")
        return True

    if command == "/search":
        if not arg:
            print("Usage: /search <query>")
            print("  Search session messages. Supports FTS5 syntax if available")
            print("  (quotes for phrase, AND/OR, prefix*, etc.)")
            return True
        sessions = runtime.session_manager.search(arg, limit=20)
        if not sessions:
            print(f"No sessions found for query: {arg}")
        else:
            print(f"Found {len(sessions)} session(s) for query: {arg}")
            print_sessions(sessions, runtime.session_manager)
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
