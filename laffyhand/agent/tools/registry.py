from typing import Any

from loguru import logger
from laffyhand.agent.schemas import ToolDefinition
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.permission import PermissionManager
from laffyhand.agent.truncation import truncate_output


class ToolRegistry:
    def __init__(self, permission: PermissionManager | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._defs: list[ToolDefinition] | None = None
        self.permission = permission or PermissionManager()

    def register_tool(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        self._defs = None

    def unregister_tool(self, name: str) -> None:
        self._tools.pop(name, None)
        self._defs = None

    def build_tool_definitions(self) -> list[ToolDefinition]:
        if self._defs is None:
            self._defs = [t.to_definition() for t in self._tools.values()]
        return self._defs

    def build_tool_prompt(self) -> str:
        lines = ["## Available tools"]
        for tool in self._tools.values():
            lines.append(f"- **{tool.name}**: {tool.description}")
        return "\n".join(lines)

    def run_tool(self, name: str, params: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            logger.warning(f"Tool '{name}' is not registered")
            return f"Tool '{name}' is not registered."

        if not self.permission.check(name):
            logger.warning(f"Tool '{name}' is not permitted")
            return f"Tool '{name}' is not permitted."

        result = tool.run(params)

        if tool.max_result_size and len(result) > tool.max_result_size:
            result = truncate_output(result, tool.max_result_size)

        return result
