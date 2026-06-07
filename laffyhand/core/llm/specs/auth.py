from abc import ABC, abstractmethod
from laffyhand.core.llm.specs.models import Header
from typing import List


class Auth(ABC):
    @abstractmethod
    def apply(self, headers: List[Header]) -> None: ...
