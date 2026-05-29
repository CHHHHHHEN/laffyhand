from abc import ABC, abstractmethod
from typing import Iterable, Generator


class Framing(ABC):
    @abstractmethod
    def frames(self, response: Iterable[bytes]) -> Generator[dict, None, None]:
        ...
