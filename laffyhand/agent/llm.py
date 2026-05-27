from typing import List, Generator, Optional

from laffyhand.agent.models import Message, StreamEvent, ToolDefinition
from laffyhand.agent.providers import BaseProvider


class LLM:
    def __init__(self, model: str, provider: BaseProvider) -> None:
        self.model = model
        self.provider = provider

    def stream(self, messages: List[Message], tools: Optional[List[ToolDefinition]] = None) -> Generator[StreamEvent, None, None]:
        yield from self.provider.chat_completions_stream(self.model, messages, tools=tools)
