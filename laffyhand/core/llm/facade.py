from collections.abc import AsyncIterator
from typing import Optional

from loguru import logger
from laffyhand.core.llm.specs.models import LLMRequest, Message, ModelID, ProviderID
from laffyhand.core.llm.specs.models import LLMEvent, ToolDefinition
from laffyhand.core.llm._route import Route


class LLM:
    def __init__(self, model: ModelID, provider: ProviderID, route: Route) -> None:
        self.model = model
        self.provider = provider
        self.route = route

    async def stream(
        self, messages: list[Message], tools: Optional[list[ToolDefinition]] = None
    ) -> AsyncIterator[LLMEvent]:
        request = LLMRequest(
            model=self.model, provider=self.provider, messages=messages, tools=tools
        )
        logger.info(f"Sending {len(messages)} messages to LLM ({self.model})")
        async for event in self.route.execute(request):
            yield event
