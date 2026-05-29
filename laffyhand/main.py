import asyncio
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
from laffyhand.agent.loop import AgentState, agent_loop

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


async def main():
    setup_logging()
    route = deepseek_route(base_url=OPENCODE_BASE_URL, api_key=OPENCODE_API_KEY)
    llm = LLM(model=OPENCODE_MODEL_NAME, route=route)
    logger.info(f"Agent session started, model={OPENCODE_MODEL_NAME}")

    # ── Skills ────────────────────────────────────────────
    skill_registry = SkillRegistry()
    skill_paths_env = os.getenv("SKILLS_PATHS", "")
    if skill_paths_env:
        skill_dirs = [d.strip() for d in skill_paths_env.split(":") if d.strip()]
    else:
        skill_dirs = ["skills/"]
    skill_registry.discover(skill_dirs)

    # ── Tools ─────────────────────────────────────────────
    tool_registry = ToolRegistry()
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

    system_content = SYSTEM_PROMPT + tool_registry.build_tool_prompt()
    if skill_registry.all():
        system_content += "\n\n" + skill_registry.build_skills_summary()
    system_message = SystemMessage(content=system_content)
    history: list = [system_message]
    compaction_config = CompactionConfig(
        tail_turns=int(os.getenv("COMPACTION_TAIL_TURNS", "2")),
    )
    state = AgentState(messages=history, turn_count=0, usage=SessionUsage(context_size=MODEL_CONTEXT_SIZE))
    max_steps = int(os.getenv("MAX_STEPS", "50"))

    while True:
        try:
            user_prompt = await asyncio.to_thread(input, "\nYou: ")
        except (EOFError, KeyboardInterrupt):
            logger.info("Agent session ended")
            break
        if user_prompt.lower() in ("", "/exit", "quit", "exit"):
            logger.info("Agent session ended")
            break

        state.step = 0
        user_message = UserMessage(content=user_prompt)
        state.messages.append(user_message)

        async for event in agent_loop(state, llm, tool_registry, compaction_config, max_steps=max_steps):
            if event.type == "content" and event.finish_reason is not None and event.usage:
                print()
                print(state.usage.display(event.usage))
            else:
                print(event.data, end="")
        print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logger.exception("Unhandled exception")
        sys.exit(1)
