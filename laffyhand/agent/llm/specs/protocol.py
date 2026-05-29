from abc import ABC, abstractmethod

from laffyhand.agent.schemas import LLMRequest, StreamEvent


class Protocol(ABC):
    @abstractmethod
    def build_request(self, request: LLMRequest) -> dict:
        ...

    @abstractmethod
    def parse_frame(self, frame: dict) -> list[StreamEvent]:
        ...
