from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator
from laffyhand.llm.specs.models import Frame


class Framing(ABC):
    @abstractmethod
    def frames(self, response: AsyncIterable[bytes]) -> AsyncIterator[Frame]: ...
