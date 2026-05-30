from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dotenv import load_dotenv
load_dotenv()

from loguru import logger
from laffyhand import setup_logging
from laffyhand.agent.schemas import (
    AgentState, CompactionConfig, SystemMessage, UserMessage, SessionUsage,
)
from laffyhand.agent.llm.builders import deepseek_route
from laffyhand.agent.llm.facade import LLM
from laffyhand.agent.session import SessionManager, TitleConfig
from laffyhand.agent.runtime import AgentRuntime
from laffyhand.agent.mcp import MCPService, LocalMCPConfig, RemoteMCPConfig


OPENCODE_BASE_URL = os.environ['OPENCODE_BASE_URL']
OPENCODE_API_KEY = os.environ['OPENCODE_API_KEY']
OPENCODE_MODEL_NAME = os.environ['OPENCODE_MODEL_NAME']
MODEL_CONTEXT_SIZE = int(os.environ['MODEL_CONTEXT_SIZE'])

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
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume the most recent active session if one exists",
    )
    parser.add_argument(
        "--session", type=str, default=None,
        help="Load a specific session by ID",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List recent sessions and exit",
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
        print(f"{s.id:<30} {s.status:<12} {title:<40} {s.message_count:<8} {cost_str:<8}")


async def resolve_session(
    args: argparse.Namespace,
    session_manager: SessionManager,
    system_message: SystemMessage,
) -> AgentState | None:
    if args.session:
        loaded = session_manager.resolve(
            args.session, system_message, MODEL_CONTEXT_SIZE,
        )
        if loaded is not None:
            logger.info(f"Loaded session {args.session} ({len(loaded.messages)} messages)")
            return loaded
        logger.error(f"Session not found: {args.session}")
        sys.exit(1)

    if args.resume:
        last_active = session_manager.get_active()
        if last_active is not None:
            loaded = session_manager.resolve(
                last_active.id, system_message, MODEL_CONTEXT_SIZE,
            )
            if loaded is not None:
                logger.info(f"Resumed session {loaded.session_id} ({len(loaded.messages)} messages)")
                return loaded
        logger.info("No active session to resume, starting new")

    session = session_manager.create(cwd=os.getcwd(), model=OPENCODE_MODEL_NAME)
    logger.info(f"New session created: {session.id}")
    return AgentState(
        messages=[system_message],
        session_id=session.id,
        usage=SessionUsage(context_size=MODEL_CONTEXT_SIZE),
    )


async def create_runtime(args: argparse.Namespace) -> AgentRuntime:
    route = deepseek_route(base_url=OPENCODE_BASE_URL, api_key=OPENCODE_API_KEY)
    llm = LLM(model=OPENCODE_MODEL_NAME, route=route)
    logger.info(f"Agent started, model={OPENCODE_MODEL_NAME}")

    mcp_service = MCPService()
    mcp_servers_json = os.getenv("MCP_SERVERS", "")
    if mcp_servers_json:
        try:
            raw: dict = json.loads(mcp_servers_json)
            mcp_configs: dict[str, LocalMCPConfig | RemoteMCPConfig] = {}
            for name, cfg in raw.items():
                if "command" in cfg:
                    mcp_configs[name] = LocalMCPConfig.model_validate(cfg)
                else:
                    mcp_configs[name] = RemoteMCPConfig.model_validate(cfg)
            await mcp_service.connect_all(mcp_configs)
        except Exception as e:
            logger.error(f"Failed to load MCP servers: {e}")

    db_path = os.getenv("DB_PATH", "./laffyhand.db")
    session_manager = SessionManager(db_path)
    title_mode: str = os.getenv("TITLE_MODE", "on_compact")
    compaction_config = CompactionConfig(
        tail_turns=int(os.getenv("COMPACTION_TAIL_TURNS", "2")),
    )
    max_steps = int(os.getenv("MAX_STEPS", "50"))
    max_subagents = int(os.getenv("MAX_CONCURRENT_SUBAGENTS", "2"))

    runtime = AgentRuntime(
        llm=llm,
        session_manager=session_manager,
        mcp_service=mcp_service,
        compaction_config=compaction_config,
        title_config=TitleConfig(mode=title_mode),  # type: ignore[arg-type]
        max_steps=max_steps,
        max_subagents=max_subagents,
        db_path=db_path,
    )

    skill_paths_env = os.getenv("SKILLS_PATHS", "")
    if skill_paths_env:
        skill_dirs = [d.strip() for d in skill_paths_env.split(":") if d.strip()]
    else:
        skill_dirs = ["skills/"]
    runtime.load_skills(skill_dirs)

    agent_paths_env = os.getenv("AGENTS_PATHS", "")
    if agent_paths_env:
        agent_dirs = [d.strip() for d in agent_paths_env.split(":") if d.strip()]
    else:
        agent_dirs = []
    runtime.load_agents(agent_dirs)

    await runtime.init_tools()
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
        _stdin_transport, _ = await loop.connect_read_pipe(
            lambda: protocol, sys.stdin
        )
        _stdin_reader = reader
    line = await _stdin_reader.readline()
    return line.decode().rstrip("\n")


async def _close_stdin_reader() -> None:
    global _stdin_reader, _stdin_transport
    if _stdin_transport is not None:
        _stdin_transport.close()
        _stdin_transport = None
    _stdin_reader = None


async def main():
    args = parse_args()
    setup_logging()

    runtime = await create_runtime(args)

    if args.list:
        sessions = runtime.session_manager.list_sessions(limit=20)
        print_sessions(sessions)
        await runtime.shutdown()
        await _close_stdin_reader()
        return

    system_content = runtime.build_system_prompt(SYSTEM_PROMPT)
    system_message = SystemMessage(content=system_content)

    state = await resolve_session(args, runtime.session_manager, system_message)
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
            if runtime.state and runtime.subagent_manager.active_count(runtime.state.session_id) > 0:
                active = runtime.subagent_manager.list_active(runtime.state.session_id)
                for sa in active:
                    print(f"  ⚙  subagent [{sa['agent_type']}] {sa['task_id'][:8]} — {sa['status']}")

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
                logger.warning(f"Unknown REPL command: {user_prompt.split()[0]}")

            if runtime.state is None:
                continue

            runtime.state.step = 0
            user_message = UserMessage(content=user_prompt)
            runtime.state.messages.append(user_message)

            if runtime.state.session_id:
                runtime.session_manager.append_messages(runtime.state.session_id, runtime.state.messages)

            if runtime.state.turn_count == 0 and runtime.title_config.mode in ("on_create", "auto"):
                gen_title = await runtime.generate_title_for_current()
                if gen_title:
                    logger.info(f"Generated session title: {gen_title}")

            async for event in runtime.run_agent_turn():
                if event.type == "content" and event.finish_reason is not None and event.usage:
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
        system_prompt = SystemMessage(content=runtime.build_system_prompt(SYSTEM_PROMPT))
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

    return False


_handle_command = handle_repl_command


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logger.exception("Unhandled exception")
        sys.exit(1)
