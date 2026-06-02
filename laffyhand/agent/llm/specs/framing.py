from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any
from laffyhand.agent.llm.specs.models import Frame

class Framing(ABC):
    @abstractmethod
    def frames(
        self, response: AsyncIterable[bytes]
    ) -> AsyncIterator[Frame]: ...
