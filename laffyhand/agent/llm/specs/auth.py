from abc import ABC, abstractmethod


class Auth(ABC):
    @abstractmethod
    def apply(self, headers: dict[str, str]) -> None:
        ...
