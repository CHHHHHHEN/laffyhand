from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from laffyhand.core.llm.specs.models import ToolDefinition


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    timeout: int = 120
    max_result_size: int | None = 10000
    path_params: list[str] = []

    ParamsModel: type[BaseModel] | None = None

    def __init__(self, **kwargs: Any) -> None:
        for key in ("timeout", "max_result_size"):
            if key in kwargs:
                setattr(self, key, kwargs[key])

    def to_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self._input_schema(),
        )

    def _input_schema(self) -> dict[str, Any]:
        if self.ParamsModel is not None:
            return self.ParamsModel.model_json_schema()
        return {"type": "object", "properties": {}}

    async def before_run(self, params: dict[str, Any]) -> dict[str, Any]:
        return params

    async def after_run(self, result: str) -> str:
        return result

    @abstractmethod
    async def run(self, params: dict[str, Any]) -> str: ...
