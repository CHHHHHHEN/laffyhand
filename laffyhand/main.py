from dotenv import load_dotenv
load_dotenv()

import os
from loguru import logger as _logger

from laffyhand.agent.models import CompactionConfig, SystemMessage, UserMessage, SessionUsage
from laffyhand.agent.providers import LLMProviderConfig, OpenAIProvider, DeepseekProvider
from laffyhand.agent.llm import LLM
from laffyhand.agent.tools import ToolRegistry, AddTool
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
    provider_config = LLMProviderConfig(name="OpenCode Go", base_url=OPENCODE_BASE_URL, api_key=OPENCODE_API_KEY)
    provider = DeepseekProvider(provider_config)
    llm = LLM(model=OPENCODE_MODEL_NAME, provider=provider)

    tool_registry = ToolRegistry()
    tool_registry.register_tool(AddTool())

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
