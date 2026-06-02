from abc import ABC, abstractmethod
from typing import List

from laffyhand.agent.llm.specs.models import Frame, LLMRequest, ProviderRequest
from laffyhand.agent.schemas import LLMEvent


class Protocol(ABC):
    @abstractmethod
    def build_request(self, request: LLMRequest) -> ProviderRequest: ...

    @abstractmethod
    def parse_frame(self, frame: Frame) -> List[LLMEvent]: ...
