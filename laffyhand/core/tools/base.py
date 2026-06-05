from abc import ABC, abstractmethod
from typing import Any

from laffyhand.core.llm.specs.models import ToolDefinition


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    max_result_size: int | None = 10000
    timeout: int = 120
    path_params: list[str] = []

    def to_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self._input_schema(),
        )

    def _input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    @abstractmethod
    async def run(self, params: dict[str, Any]) -> str: ...
