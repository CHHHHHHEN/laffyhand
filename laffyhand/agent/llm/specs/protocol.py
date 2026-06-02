from abc import ABC, abstractmethod
from typing import ClassVar, List

from laffyhand.agent.llm.specs.models import Frame, LLMRequest, ProviderRequest, ProviderID
from laffyhand.agent.schemas import LLMEvent


class Protocol(ABC):
    provider_id: ClassVar[ProviderID]

    @abstractmethod
    def build_request(self, request: LLMRequest) -> ProviderRequest: ...

    @abstractmethod
    def parse_frame(self, frame: Frame) -> List[LLMEvent]: ...
