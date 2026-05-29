from typing import Any

from laffyhand.agent.schemas import ToolDefinition, ToolResultContent
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.permission import PermissionManager
from laffyhand.agent.tools.truncation import truncate_output


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
            lines.append(tool.name)
            lines.append(tool.description)
            lines.append("")
        return "\n".join(lines)

    # TODO: 添加 ThreadPoolExecutor 并行执行，参考 hermes-agent tool_executor.py

    def run_tool(self, name: str, params: dict[str, Any], tool_call_id: str = "") -> ToolResultContent:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResultContent(
                tool_call_id=tool_call_id,
                tool_name=name,
                result=f"Tool '{name}' is not registered.",
            )

        if not self.permission.check(name):
            return ToolResultContent(
                tool_call_id=tool_call_id,
                tool_name=name,
                result=f"Tool '{name}' is not permitted.",
            )

        result = tool.run(params)
        result.tool_call_id = tool_call_id
        result.tool_name = name

        if tool.max_result_size and len(result.result) > tool.max_result_size:
            result.result = truncate_output(result.result, tool.max_result_size)

        return result
