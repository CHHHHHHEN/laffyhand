import asyncio
from collections.abc import Callable
from typing import Any

from loguru import logger
from laffyhand.core.llm.specs.models import ToolDefinition
from laffyhand.core.tools.base import BaseTool
from laffyhand.core.tools.permission import PermissionManager
from laffyhand.core._utils import truncate_output


class ToolRegistry:
    def __init__(self, permission: PermissionManager | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._defs: list[ToolDefinition] = []
        self._dirty = True
        self.permission = permission or PermissionManager()
        self._on_build_defs: list[Callable[[], None]] = []
        self._lock = asyncio.Lock()
        self.result_post_processor: Callable[[str, str, dict[str, Any]], str] | None = None
        self.workspace: str | None = None

    def on_build_defs(self, callback: Callable[[], None]) -> None:
        self._on_build_defs.append(callback)

    def register_tool(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        self._dirty = True

    def unregister_tool(self, name: str) -> None:
        self._tools.pop(name, None)
        self._dirty = True

    def list_tools(self) -> dict[str, BaseTool]:
        return dict(self._tools)

    async def build_tool_definitions(
        self, exclude: set[str] | None = None,
    ) -> list[ToolDefinition]:
        async with self._lock:
            if self._dirty:
                for cb in self._on_build_defs:
                    cb()
                self._defs = [t.to_definition() for t in self._tools.values()]
                self._dirty = False
                logger.debug(
                    f"Built {len(self._defs)} tool definition(s): {[d.name for d in self._defs]}"
                )
        if exclude:
            return [d for d in self._defs if d.name not in exclude]
        return self._defs

    def _format_params(self, schema: dict[str, Any]) -> str:
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        if not props:
            return ""
        parts = []
        for name, prop in props.items():
            opt = "" if name in required else "?"
            parts.append(f"{name}{opt}")
        return f"({', '.join(parts)})" if parts else ""

    def build_tool_prompt(self, exclude: set[str] | None = None) -> str:
        lines = ["<tools>"]
        for tool in self._tools.values():
            if exclude and tool.name in exclude:
                continue
            params = self._format_params(tool.to_definition().input_schema)
            lines.append(f"- **{tool.name}**{params}: {tool.description}")
        lines.append("</tools>")
        return "\n".join(lines)

    async def run_tool(self, name: str, params: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None and " " in name:
            # Some LLMs conflate tool name with operation (e.g. "tag update").
            # Split on first space and try to extract the operation.
            base, _, candidate_op = name.partition(" ")
            tool = self._tools.get(base)
            if tool is not None:
                logger.info(
                    f"Compound tool name '{name}' resolved as '{base}' "
                    f"with operation '{candidate_op}'"
                )
                if "operation" not in params:
                    params = dict(params, operation=candidate_op)
                name = base
        if tool is None:
            logger.warning(f"Tool '{name}' is not registered")
            return f"Tool '{name}' is not registered."

        if not self.permission.check(name):
            logger.warning(f"Tool '{name}' is not permitted")
            return f"Tool '{name}' is not permitted."

        logger.info(f"Running tool: {name}")

        if self.workspace is not None:
            for param_name in tool.path_params:
                raw = params.get(param_name)
                if raw is None:
                    continue
                values: list[str] = [raw] if isinstance(raw, str) else (raw if isinstance(raw, list) else [])
                for p in values:
                    ok, reason = await self.permission.require_path(name, p, self.workspace)
                    if not ok:
                        return reason or f"Error: Access to '{p}' outside workspace was denied."

        timeout = getattr(tool, "timeout", 120)
        try:
            if timeout and timeout > 0:
                result = await asyncio.wait_for(tool.run(params), timeout=timeout)
            else:
                result = await tool.run(params)
        except asyncio.TimeoutError:
            logger.warning(f"Tool '{name}' timed out after {timeout}s")
            return f"Error: Tool '{name}' timed out after {timeout}s. Try a more specific query or reduce scope."

        if self.result_post_processor is not None:
            result = self.result_post_processor(name, result, params)

        if tool.max_result_size and len(result) > tool.max_result_size:
            result = truncate_output(result, tool.max_result_size)

        return result
