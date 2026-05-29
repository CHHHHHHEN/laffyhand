from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator


class Framing(ABC):
    @abstractmethod
    def frames(self, response: AsyncIterable[bytes]) -> AsyncIterator[dict]:
        ...
