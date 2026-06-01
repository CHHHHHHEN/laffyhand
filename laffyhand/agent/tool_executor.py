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

    # ── Word/chunk deduplication ──────────────────────────────────
    # Some LLMs double every word/token in keys and string values,
    # either as whole-word duplication ("commandcommand") or
    # per-chunk duplication ("ppwdwd" from "p"+"wd" chunks).
    # Strategy 1: exact word duplication (e.g. "commandcommand")
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

    # Strategy 2: chunk-level doubling — try to find consecutive
    # repeated substrings of varying lengths.  Handles cases like:
    #   "ppwdwd"  ← "p"+"wd" chunks each doubled
    #   "获取获取当前当前工作工作目录目录"  ← each CJK chunk doubled
    #   "获取获取" → "获取"
    #
    # The approach: for each JSON key or string value, try a greedy
    # scan that removes one copy when the string looks like it's
    # composed of doubled chunks.
    import re as _re

    def _dedup_chunks(s: str) -> str:
        """Try to remove consecutive doubled chunks from a string."""
        if len(s) < 2:
            return s
        # If the whole string is exactly doubled, short-circuit
        half = len(s) // 2
        if half >= 1 and s[:half] == s[half:]:
            return s[:half]
        # Greedy scan: for increasing chunk sizes, see if the string
        # consists of pairs of identical chunks.
        out: list[str] = []
        i = 0
        n = len(s)
        while i < n:
            best = 1  # minimum chunk size
            found = False
            # Try chunk sizes from longest to shortest for better matching
            for clen in range((n - i) // 2, 0, -1):
                if i + 2 * clen <= n and s[i : i + clen] == s[i + clen : i + 2 * clen]:
                    out.append(s[i : i + clen])
                    i += 2 * clen
                    found = True
                    break
            if not found:
                out.append(s[i])
                i += 1
        return "".join(out)

    # Apply to all JSON string values and keys
    def _apply_chunk_dedup(m: _re.Match[str]) -> str:
        return _dedup_chunks(m.group(1))

    cleaned = _re.sub(
        r'"((?:[^"\\]|\\.)*)"',  # match JSON string contents
        lambda m: '"' + _dedup_chunks(m.group(1)) + '"',
        cleaned,
    )

    try:
        return cast(dict[str, Any], json.loads(cleaned))
    except json.JSONDecodeError:
        pass

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
