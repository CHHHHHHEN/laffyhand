from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from laffyhand.agent.llm.specs.models import ToolMessage
from laffyhand.agent.schemas import ToolCallContent

if TYPE_CHECKING:
    from laffyhand.agent.tools.registry import ToolRegistry


@dataclass
class ToolExecutionResult:
    message: ToolMessage
    event_data: str
    is_error: bool


def _try_parse_json(raw: str) -> dict[str, Any] | None:
    """Best-effort JSON parsing with recovery for common LLM-induced issues.

    LLMs sometimes generate tool-call arguments with doubled structural
    characters or word duplication (e.g. ``commandcommand``).  This
    function tries multiple strategies before giving up.
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
    # Some LLMs double entire words in keys and string values
    # (e.g. "commandcommand" instead of "command").
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
        return cast(dict[str, Any], json.loads(cleaned))
    except json.JSONDecodeError:
        pass

    return None


class ToolExecutor:
    @staticmethod
    async def execute(
        tool_registry: ToolRegistry,
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
                    content=f"Error: failed to parse tool arguments for {tool_call.tool_name}. "
                    f'Args must be valid JSON object like {{"key": "value"}}. '
                    f"Received: {tool_call.args}",
                    is_error=True,
                ),
                event_data=f"Error: invalid JSON args for {tool_call.tool_name}",
                is_error=True,
            )

        # Inject runtime context into params (e.g. session_id).
        # Strip any LLM-provided values for keys the runtime controls,
        # so runtime context always takes precedence.
        if context:
            for key in context:
                params.pop(key, None)
            params.update(context)

        try:
            result = await tool_registry.run_tool(tool_call.tool_name, params)
        except Exception as e:
            logger.exception(f"Tool execution failed for {tool_call.tool_name}: {e}")
            return ToolExecutionResult(
                message=ToolMessage(
                    tool_call_id=tool_call.tool_call_id,
                    content=f"Error executing tool {tool_call.tool_name}: internal error",
                    is_error=True,
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
