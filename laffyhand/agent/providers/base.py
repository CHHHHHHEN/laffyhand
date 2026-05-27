from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List, Generator, Optional

from laffyhand.agent.models import Message, StreamEvent, ToolDefinition


class LLMProviderConfig(BaseModel):
    name: str
    base_url: str
    api_key: str


class BaseProvider(ABC):
    def __init__(self, config: LLMProviderConfig):
        self.config = config

    @abstractmethod
    def chat_completions_stream(
        self, model: str, messages: List[Message], tools: Optional[List[ToolDefinition]] = None
    ) -> Generator[StreamEvent, None, None]:
        ...
