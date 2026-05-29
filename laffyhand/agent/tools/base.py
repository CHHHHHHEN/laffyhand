from abc import ABC, abstractmethod
from typing import Any

from laffyhand.agent.schemas import ToolDefinition, ToolResultContent


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    max_result_size: int | None = 10000

    def to_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self._input_schema(),
        )

    def _input_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    @abstractmethod
    def run(self, params: dict[str, Any]) -> ToolResultContent:
        ...
