from collections.abc import Callable
from typing import Any

from loguru import logger
from laffyhand.agent.schemas import ToolDefinition
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.permission import PermissionManager
from laffyhand.agent.truncation import truncate_output


class ToolRegistry:
    def __init__(self, permission: PermissionManager | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._defs: list[ToolDefinition] = []
        self._dirty = True
        self.permission = permission or PermissionManager()
        self._on_build_defs: list[Callable[[], None]] = []

    def on_build_defs(self, callback: Callable[[], None]) -> None:
        self._on_build_defs.append(callback)

    def register_tool(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        self._dirty = True

    def unregister_tool(self, name: str) -> None:
        self._tools.pop(name, None)
        self._dirty = True

    def build_tool_definitions(self) -> list[ToolDefinition]:
        for cb in self._on_build_defs:
            cb()
            self._dirty = True
        if self._dirty:
            self._defs = [t.to_definition() for t in self._tools.values()]
            self._dirty = False
            logger.debug(f"Built {len(self._defs)} tool definition(s): {[d.name for d in self._defs]}")
        return self._defs

    def build_tool_prompt(self) -> str:
        lines = ["## Available tools"]
        for tool in self._tools.values():
            lines.append(f"- **{tool.name}**: {tool.description}")
        return "\n".join(lines)

    async def run_tool(self, name: str, params: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            logger.warning(f"Tool '{name}' is not registered")
            return f"Tool '{name}' is not registered."

        if not self.permission.check(name):
            logger.warning(f"Tool '{name}' is not permitted")
            return f"Tool '{name}' is not permitted."

        logger.info(f"Running tool: {name}")
        result = await tool.run(params)

        if tool.max_result_size and len(result) > tool.max_result_size:
            result = truncate_output(result, tool.max_result_size)

        return result
