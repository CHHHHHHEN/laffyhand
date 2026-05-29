from typing import Generator, Optional

from laffyhand.agent.schemas import LLMRequest, Message, StreamEvent, ToolDefinition
from laffyhand.agent.llm._route import Route


class LLM:
    def __init__(self, model: str, route: Route) -> None:
        self.model = model
        self.route = route

    def stream(
        self, messages: list[Message], tools: Optional[list[ToolDefinition]] = None
    ) -> Generator[StreamEvent, None, None]:
        request = LLMRequest(model=self.model, messages=messages, tools=tools)
        yield from self.route.execute(request)
