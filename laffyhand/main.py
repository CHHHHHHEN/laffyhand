from dotenv import load_dotenv
load_dotenv()

import os

from laffyhand.agent.schemas import CompactionConfig, SystemMessage, UserMessage, SessionUsage
from laffyhand.agent.llm.builders import deepseek_route
from laffyhand.agent.llm.facade import LLM
from laffyhand.agent.tools import ToolRegistry
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


def main():
    route = deepseek_route(base_url=OPENCODE_BASE_URL, api_key=OPENCODE_API_KEY)
    llm = LLM(model=OPENCODE_MODEL_NAME, route=route)

    tool_registry = ToolRegistry()
    tool_registry.register_tool(ReadTool())
    tool_registry.register_tool(WriteTool())
    tool_registry.register_tool(EditTool())
    tool_registry.register_tool(GlobTool())
    tool_registry.register_tool(GrepTool())
    tool_registry.register_tool(BashTool())
    tool_registry.register_tool(TodoTool(todo_path="/home/ch/src/laffyhand/.todos.json"))

    system_message = SystemMessage(content=SYSTEM_PROMPT + tool_registry.build_tool_prompt())
    history: list = [system_message]
    compaction_config = CompactionConfig(
        tail_turns=int(os.getenv("COMPACTION_TAIL_TURNS", "2")),
    )
    state = AgentState(messages=history, turn_count=0, usage=SessionUsage(context_size=MODEL_CONTEXT_SIZE))

    user_prompt = input("Type message: ")
    user_message = UserMessage(content=user_prompt)
    state.messages.append(user_message)

    for event in agent_loop(state, llm, tool_registry, compaction_config):
        if event.type == "content" and event.finish_reason is not None and event.usage:
            print()
            print(state.usage.display(event.usage))
        else:
            print(event.data, end="")
    print()


if __name__ == "__main__":
    main()
