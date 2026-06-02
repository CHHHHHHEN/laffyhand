from collections.abc import AsyncIterator
from typing import Optional

from loguru import logger
from laffyhand.agent.llm.specs.models import LLMRequest, Message
from laffyhand.agent.schemas import LLMEvent, ToolDefinition
from laffyhand.agent.llm._route import Route


class LLM:
    def __init__(self, model: str, route: Route) -> None:
        self.model = model
        self.route = route

    async def stream(
        self, messages: list[Message], tools: Optional[list[ToolDefinition]] = None
    ) -> AsyncIterator[LLMEvent]:
        request = LLMRequest(model=self.model, messages=messages, tools=tools)
        logger.info(f"Sending {len(messages)} messages to LLM ({self.model})")
        async for event in self.route.execute(request):
            yield event
