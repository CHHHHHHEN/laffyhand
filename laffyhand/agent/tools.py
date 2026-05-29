from typing import Dict, Any, List, override
from abc import ABC, abstractmethod

from laffyhand.agent.schemas import ToolDefinition, ToolResultContent

ToolResult = ToolResultContent


class BaseTool(ABC):
    name: str
    description: str

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self._input_schema(),
        )

    def _input_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    @abstractmethod
    def run(self, params: Dict[str, Any]) -> ToolResult:
        ...

class AddTool(BaseTool):
    name = "add"
    description = "Add number a and b, return result c."

    def _input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"},
            },
            "required": ["a", "b"],
        }

    @override
    def run(self, params: Dict[str, Any]) -> ToolResult:
        added = int(params["a"]) + int(params["b"])
        return ToolResult(tool_call_id="", tool_name=self.name, result=str(added))

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register_tool(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def unregister_tool(self, tool: BaseTool) -> None:
        del self._tools[tool.name]

    def build_tool_prompt(self) -> str:
        lines = ["## Available tools"]
        for tool in self._tools.values():
            lines.append(tool.name)
            lines.append(tool.description)
            lines.append("\n")
        return "\n".join(lines)

    def build_tool_definitions(self) -> List[ToolDefinition]:
        return [tool.definition for tool in self._tools.values()]

    def run_tool(self, name: str, params: Dict[str, Any]) -> ToolResult:
        return self._tools[name].run(params)