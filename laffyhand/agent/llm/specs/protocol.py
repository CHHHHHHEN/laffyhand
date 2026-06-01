from abc import ABC, abstractmethod
from typing import Any

from laffyhand.agent.schemas import LLMRequest, StreamEvent


class Protocol(ABC):
    @abstractmethod
    def build_request(self, request: LLMRequest) -> dict[str, Any]: ...

    @abstractmethod
    def parse_frame(self, frame: dict[str, Any]) -> list[StreamEvent]: ...
