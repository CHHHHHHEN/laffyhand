from abc import ABC, abstractmethod


class Endpoint(ABC):
    @abstractmethod
    def build(self) -> str: ...
