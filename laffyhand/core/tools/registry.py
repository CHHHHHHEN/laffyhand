import asyncio
import json
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger
from laffyhand.core.llm.specs.models import ToolDefinition, ToolCallContent, ToolMessage
from laffyhand.core.tools.base import BaseTool
from laffyhand.core.tools.permission import PermissionManager
from laffyhand.core._utils import truncate_output


@dataclass
class ToolExecutionResult:
    message: ToolMessage
    event_data: str
    is_error: bool


def _try_parse_json(raw: str) -> dict[str, Any] | None:
    cleaned = raw.strip()
    if not cleaned:
        logger.warning("Empty JSON args, skipping repair")
        return None

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    replacements = [
        ("{{", "{"),
        ("}}", "}"),
        ('""', '"'),
        ("::", ":"),
        (",,", ","),
    ]
    for old, new in replacements:
        cleaned = cleaned.replace(old, new)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    def _dedup_exact(m: re.Match[str]) -> str:
        word = m.group(0)
        half = len(word) // 2
        if half >= 2 and word[:half] == word[half:]:
            return word[:half]
        return word

    cleaned = re.sub(
        r'(?<=["\'])\w{4,}(?=["\'])|(?<=[\s,{])\w{4,}(?=[:])', _dedup_exact, cleaned
    )

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    return None


class ToolRegistry:
    def __init__(self, permission: PermissionManager | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._defs: list[ToolDefinition] = []
        self._dirty = True
        self.permission = permission or PermissionManager()
        self._on_build_defs: list[Callable[[], None]] = []
        self._lock = threading.Lock()
        self.result_post_processor: Callable[[str, str, dict[str, Any]], str] | None = (
            None
        )
        self.workspace: str | None = None

    def on_build_defs(self, callback: Callable[[], None]) -> None:
        self._on_build_defs.append(callback)

    def register_tool(self, tool: BaseTool) -> None:
        with self._lock:
            self._tools[tool.name] = tool
            self._dirty = True

    def unregister_tool(self, name: str) -> None:
        with self._lock:
            self._tools.pop(name, None)
            self._dirty = True

    def unregister_by_prefix(self, prefix: str) -> int:
        unregistered = 0
        with self._lock:
            for tool_name in list(self._tools):
                if tool_name.startswith(prefix):
                    self._tools.pop(tool_name, None)
                    unregistered += 1
            if unregistered:
                self._dirty = True
        return unregistered

    def list_tools(self) -> dict[str, BaseTool]:
        with self._lock:
            return dict(self._tools)

    async def build_tool_definitions(
        self,
        exclude: set[str] | None = None,
    ) -> list[ToolDefinition]:
        with self._lock:
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

    async def execute_tool_call(
        self,
        tool_call: ToolCallContent,
        context: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        params = _try_parse_json(tool_call.args)
        if params is None:
            logger.warning(
                f"Failed to parse tool args for {tool_call.tool_name}: {tool_call.args[:200]}"
            )
            return ToolExecutionResult(
                message=ToolMessage(
                    tool_call_id=tool_call.tool_call_id,
                    tool_name=tool_call.tool_name,
                    args=tool_call.args,
                    content=f"Error: failed to parse tool arguments for {tool_call.tool_name}. "
                    f'Args must be valid JSON object like {{"key": "value"}}. '
                    f"Received: {tool_call.args}",
                    is_error=True,
                ),
                event_data=f"Error: invalid JSON args for {tool_call.tool_name}",
                is_error=True,
            )

        if context:
            for key in context:
                params.pop(key, None)
            params.update(context)

        try:
            result = await self.run_tool(tool_call.tool_name, params)
        except Exception as e:
            logger.exception(f"Tool execution failed for {tool_call.tool_name}: {e}")
            return ToolExecutionResult(
                message=ToolMessage(
                    tool_call_id=tool_call.tool_call_id,
                    tool_name=tool_call.tool_name,
                    args=tool_call.args,
                    content=f"Error executing tool {tool_call.tool_name}: internal error",
                    is_error=True,
                ),
                event_data=f"Error: {tool_call.tool_name} failed: internal error",
                is_error=True,
            )

        return ToolExecutionResult(
            message=ToolMessage(
                tool_call_id=tool_call.tool_call_id,
                tool_name=tool_call.tool_name,
                args=tool_call.args,
                content=result,
            ),
            event_data=result,
            is_error=False,
        )

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
                values: list[str] = (
                    [raw]
                    if isinstance(raw, str)
                    else (raw if isinstance(raw, list) else [])
                )
                for p in values:
                    ok, reason = await self.permission.require_path(
                        name, p, self.workspace
                    )
                    if not ok:
                        return (
                            reason
                            or f"Error: Access to '{p}' outside workspace was denied."
                        )

        params = await tool.before_run(params)

        timeout = getattr(tool, "timeout", 120)
        try:
            if timeout and timeout > 0:
                result = await asyncio.wait_for(tool.run(params), timeout=timeout)
            else:
                result = await tool.run(params)
        except asyncio.TimeoutError:
            logger.warning(f"Tool '{name}' timed out after {timeout}s")
            return f"Error: Tool '{name}' timed out after {timeout}s. Try a more specific query or reduce scope."

        result = await tool.after_run(result)

        if self.result_post_processor is not None:
            result = self.result_post_processor(name, result, params)

        if tool.max_result_size and len(result) > tool.max_result_size:
            result = truncate_output(result, tool.max_result_size)

        return result
