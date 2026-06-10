from abc import ABC, abstractmethod
from typing import ClassVar, List

from laffyhand.core.domain.messages import ProviderID
from laffyhand.core.llm.specs.models import (
    Frame,
    LLMRequest,
    ProviderRequest,
)
from laffyhand.core.llm.specs.models import LLMEvent


class Protocol(ABC):
    provider_id: ClassVar[ProviderID]

    @abstractmethod
    def build_request(self, request: LLMRequest) -> ProviderRequest: ...

    @abstractmethod
    def parse_frame(self, frame: Frame) -> List[LLMEvent]: ...
