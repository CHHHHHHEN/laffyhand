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
from laffyhand.agent.schemas import CompactionConfig, SystemMessage, UserMessage, SessionUsage
from laffyhand.agent.skill import SkillRegistry
from laffyhand.agent.llm.builders import deepseek_route
from laffyhand.agent.llm.facade import LLM
from laffyhand.agent.tools import ToolRegistry, SkillTool
from laffyhand.agent.tools.file import ReadTool, WriteTool, EditTool, GlobTool, GrepTool
from laffyhand.agent.tools.bash import BashTool
from laffyhand.agent.tools.todo import TodoTool
from laffyhand.agent.mcp import MCPService, LocalMCPConfig, RemoteMCPConfig
from laffyhand.agent.loop import AgentState, agent_loop
from laffyhand.agent.session import SessionManager, TitleConfig

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
) -> AgentState:
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


async def handle_repl_command(
    cmd: str,
    state: AgentState,
    session_manager: SessionManager,
    llm: LLM,
    title_config: TitleConfig,
) -> bool:
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command == "/sessions":
        sessions = session_manager.list_sessions(limit=20)
        print_sessions(sessions)
        logger.info(f"Listed {len(sessions)} sessions")
        return True

    if command == "/session":
        if not arg:
            print("Usage: /session <id>")
            return True
        # Save current state before switching
        if state.session_id and session_manager.get(state.session_id):
            session_manager.save_state(state.session_id, state)
        tip = session_manager.get_compression_tip(arg)
        loaded = session_manager.load_state(tip)
        if loaded is None:
            print(f"Session not found: {arg}")
            return True
        state.messages = loaded.messages
        state.turn_count = loaded.turn_count
        state.step = loaded.step
        state.usage = loaded.usage
        state.session_id = loaded.session_id
        logger.info(f"Switched to session: {tip}")
        print(f"Switched to session: {tip}")
        return True

    if command == "/new":
        if state.session_id:
            if session_manager.get(state.session_id):
                session_manager.save_state(state.session_id, state)
            session_manager.complete(state.session_id)
        session = session_manager.create(
            cwd=os.getcwd(),
            model=OPENCODE_MODEL_NAME,
        )
        state.messages = [state.messages[0]] if state.messages else []
        state.session_id = session.id
        state.turn_count = 0
        state.step = 0
        state.usage = SessionUsage(context_size=MODEL_CONTEXT_SIZE)
        logger.info(f"New session started: {session.id}")
        print(f"New session started: {session.id}")
        return True

    if command == "/title":
        if arg:
            if state.session_id:
                session_manager.set_title(state.session_id, arg)
                logger.info(f"Title set for {state.session_id}: {arg}")
                print(f"Title set to: {arg}")
            else:
                print("No active session.")
        elif state.session_id:
            from laffyhand.agent.context import generate_title
            gen_title = await generate_title(
                session_manager, state.session_id, llm, title_config,
            )
            if gen_title:
                print(f"Generated title: {gen_title}")
            else:
                print("Could not generate title.")
        return True

    if command == "/fork":
        if not state.session_id:
            print("No active session to fork.")
            return True
        child = session_manager.fork(state.session_id)
        state.session_id = child.id
        logger.info(f"Forked to new session: {child.id}")
        print(f"Forked to new session: {child.id}")
        return True

    if command == "/archive":
        target = arg or state.session_id
        if target:
            session_manager.archive(target)
            logger.info(f"Archived session: {target}")
            print(f"Archived session: {target}")
        return True

    return False


async def main():
    args = parse_args()
    setup_logging()
    route = deepseek_route(base_url=OPENCODE_BASE_URL, api_key=OPENCODE_API_KEY)
    llm = LLM(model=OPENCODE_MODEL_NAME, route=route)
    logger.info(f"Agent started, model={OPENCODE_MODEL_NAME}")

    # ── Session manager ──────────────────────────────────────
    db_path = os.getenv("DB_PATH", "./laffyhand.db")
    session_manager = SessionManager(db_path)

    title_mode = os.getenv("TITLE_MODE", "on_compact")
    title_config = TitleConfig(mode=title_mode)

    # ── Skills ────────────────────────────────────────────────
    skill_registry = SkillRegistry()
    skill_paths_env = os.getenv("SKILLS_PATHS", "")
    if skill_paths_env:
        skill_dirs = [d.strip() for d in skill_paths_env.split(":") if d.strip()]
    else:
        skill_dirs = ["skills/"]
    skill_registry.discover(skill_dirs)

    # ── MCP ───────────────────────────────────────────────────
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

    # ── Tools ─────────────────────────────────────────────────
    tool_registry = ToolRegistry()
    for mcp_tool in await mcp_service.get_wrapped_tools():
        tool_registry.register_tool(mcp_tool)
    tool_registry.register_tool(ReadTool())
    tool_registry.register_tool(WriteTool())
    tool_registry.register_tool(EditTool())
    tool_registry.register_tool(GlobTool())
    tool_registry.register_tool(GrepTool())
    tool_registry.register_tool(BashTool())
    tool_registry.register_tool(TodoTool(todo_path=os.getenv("TODOS_PATH", ".todos.json")))

    skill_tool = SkillTool(skill_registry, tool_registry.permission)
    tool_registry.register_tool(skill_tool)

    def _update_skill_description():
        summary = skill_registry.build_skills_summary()
        if summary:
            skill_tool.description = f"Load and inject a skill into context.\n\nAvailable skills:\n{summary}"
        else:
            skill_tool.description = "Load and inject a skill into context."
    tool_registry.on_build_defs(_update_skill_description)
    _update_skill_description()

    # ── System prompt ─────────────────────────────────────────
    system_content = SYSTEM_PROMPT + tool_registry.build_tool_prompt()
    if skill_registry.all():
        system_content += "\n\n" + skill_registry.build_skills_summary()
    system_message = SystemMessage(content=system_content)

    # ── Session resolution ────────────────────────────────────
    if args.list:
        sessions = session_manager.list_sessions(limit=20)
        print_sessions(sessions)
        await mcp_service.disconnect_all()
        return

    state = await resolve_session(args, session_manager, system_message)

    compaction_config = CompactionConfig(
        tail_turns=int(os.getenv("COMPACTION_TAIL_TURNS", "2")),
    )
    max_steps = int(os.getenv("MAX_STEPS", "50"))

    print(f"\nSession: {state.session_id}")
    if state.turn_count > 0:
        print(f"Resuming conversation ({state.turn_count} previous turns)")

    try:
        while True:
            try:
                user_prompt = await asyncio.to_thread(input, "\nYou: ")
            except (EOFError, KeyboardInterrupt):
                logger.info("Agent session ended")
                break

            if user_prompt.lower() in ("", "/exit", "quit", "exit"):
                logger.info("Agent session ended")
                break

            # ── Handle REPL commands ──────────────────────────
            if user_prompt.startswith("/"):
                handled = await handle_repl_command(
                    user_prompt, state, session_manager, llm, title_config,
                )
                if handled:
                    continue
                logger.warning(f"Unknown REPL command: {user_prompt.split()[0]}")

            # ── Append user message ───────────────────────────
            state.step = 0
            user_message = UserMessage(content=user_prompt)
            state.messages.append(user_message)

            # ── Persist user message immediately ──────────────
            if state.session_id:
                session_manager.append_messages(state.session_id, state.messages)

            # ── Generate title on first user message ──────────
            if state.turn_count == 0 and title_config.mode in ("on_create", "auto"):
                from laffyhand.agent.context import generate_title
                gen_title = await generate_title(
                    session_manager, state.session_id, llm, title_config,
                )
                if gen_title:
                    logger.info(f"Generated session title: {gen_title}")

            # ── Run agent loop ────────────────────────────────
            async for event in agent_loop(
                state, llm, tool_registry, compaction_config,
                max_steps=max_steps,
                session_manager=session_manager,
            ):
                if event.type == "content" and event.finish_reason is not None and event.usage:
                    print()
                    print(state.usage.display(event.usage))
                else:
                    print(event.data, end="")
            print()
    finally:
        if state.session_id:
            session_manager.save_state(state.session_id, state)
            logger.info(f"Session state saved: {state.session_id}")
        await mcp_service.disconnect_all()
        session_manager.close()
        logger.info("Agent shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logger.exception("Unhandled exception")
        sys.exit(1)
