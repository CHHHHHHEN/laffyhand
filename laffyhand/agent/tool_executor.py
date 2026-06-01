from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from laffyhand.agent.schemas import ToolCallContent, ToolMessage

if TYPE_CHECKING:
    from laffyhand.agent.tools.registry import ToolRegistry


@dataclass
class ToolExecutionResult:
    message: ToolMessage
    event_data: str
    is_error: bool


def _try_parse_json(raw: str) -> dict[str, Any] | None:
    """Best-effort JSON parsing with recovery for common LLM-induced issues.

    LLMs sometimes generate tool-call arguments with doubled characters
    (e.g. ``{{""commandcommand"": : ""ppwdwd""}}`` instead of
    ``{"command": "pwd"}``).  This function tries multiple strategies
    before giving up.
    """
    cleaned = raw.strip()
    if not cleaned:
        logger.warning("Empty JSON args, skipping repair")
        return None

    # Direct parse first
    try:
        return cast(dict[str, Any], json.loads(cleaned))
    except json.JSONDecodeError:
        pass

    # ── Structural fixes ──────────────────────────────────────────
    # Some LLMs double every structural character.
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
        return cast(dict[str, Any], json.loads(cleaned))
    except json.JSONDecodeError:
        pass

    # ── Word deduplication ────────────────────────────────────────
    # Some LLMs double every word in keys and string values.
    # Remove the second occurrence of any consecutive identical token.
    # This handles: "commandcommand" -> "command",
    # "获取获取" -> "获取", etc.
    def _dedup(m: re.Match[str]) -> str:
        word = m.group(0)
        half = len(word) // 2
        if len(word) >= 4 and word[:half] == word[half:]:
            return word[:half]
        return word

    # Match JSON string contents (between quotes), key names, and bare words
    cleaned = re.sub(
        r'(?<=["\'])\w{4,}(?=["\'])|(?<=[\s,{])\w{4,}(?=[:])', _dedup, cleaned
    )

    try:
        return cast(dict[str, Any], json.loads(cleaned))
    except json.JSONDecodeError:
        pass

    return None


class ToolExecutor:
    @staticmethod
    async def execute(
        tool_registry: ToolRegistry,
        tool_call: ToolCallContent,
    ) -> ToolExecutionResult:
        params = _try_parse_json(tool_call.args)
        if params is None:
            logger.warning(
                f"Failed to parse tool args for {tool_call.tool_name}: {tool_call.args[:200]}"
            )
            return ToolExecutionResult(
                message=ToolMessage(
                    tool_call_id=tool_call.tool_call_id,
                    content=f"Error: failed to parse tool arguments for {tool_call.tool_name}. "
                    f'Args must be valid JSON object like {{"key": "value"}}. '
                    f"Received: {tool_call.args}",
                ),
                event_data=f"Error: invalid JSON args for {tool_call.tool_name}",
                is_error=True,
            )

        try:
            result = await tool_registry.run_tool(tool_call.tool_name, params)
        except Exception as e:
            logger.exception(f"Tool execution failed for {tool_call.tool_name}: {e}")
            return ToolExecutionResult(
                message=ToolMessage(
                    tool_call_id=tool_call.tool_call_id,
                    content=f"Error executing tool {tool_call.tool_name}: internal error",
                ),
                event_data=f"Error: {tool_call.tool_name} failed: internal error",
                is_error=True,
            )

        return ToolExecutionResult(
            message=ToolMessage(
                tool_call_id=tool_call.tool_call_id,
                content=result,
            ),
            event_data=result,
            is_error=False,
        )
