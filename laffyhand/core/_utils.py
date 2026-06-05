from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from laffyhand.core.llm.specs.models import (
    AssistantMessage, Message, SystemMessage, ToolMessage, UserMessage,
)


CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(0, round(len(text) / CHARS_PER_TOKEN))


def estimate_message_tokens(msg: Message) -> int:
    total = 0
    if isinstance(msg, (SystemMessage, UserMessage)):
        total += estimate_tokens(msg.content)
    elif isinstance(msg, AssistantMessage):
        if msg.content:
            total += estimate_tokens(msg.content)
        if msg.reasoning:
            total += estimate_tokens(msg.reasoning)
        if msg.tool_calls:
            for tc in msg.tool_calls:
                total += estimate_tokens(tc.tool_name + tc.args)
    elif isinstance(msg, ToolMessage):
        total += estimate_tokens(msg.content)
    return total


def estimate_messages_tokens(messages: list[Message]) -> int:
    return sum(estimate_message_tokens(m) for m in messages)


_DEFAULT_TRUNCATE = 2000


def _unwrap_json_string(value: str) -> Any | None:
    try:
        parsed = json.loads(value)
        if isinstance(parsed, str):
            return json.loads(parsed)
        return parsed
    except (json.JSONDecodeError, TypeError):
        return None


def coerce_json_dict(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return {k: str(v) for k, v in value.items()}
    if isinstance(value, str):
        parsed = _unwrap_json_string(value)
        if isinstance(parsed, dict):
            return {k: str(v) for k, v in parsed.items()}
    return {}


def coerce_json_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        parsed = _unwrap_json_string(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def exponential_backoff(base: float, attempt: int, max_delay: float = 60.0) -> float:
    return min(base * (2 ** (attempt - 1)), max_delay)


def build_env_block(workspace: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    parts = [
        f"Working directory: {os.getcwd()}",
        f"Workspace: {workspace or os.getcwd()}",
        f"Platform: {sys.platform}",
        f"Current time: {now.isoformat()}",
    ]
    return "<env>\n" + "\n".join(parts) + "\n</env>"


def truncate_output(text: str | None, max_chars: int = _DEFAULT_TRUNCATE) -> str:
    if text is None:
        return ""
    if not text or len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    logger.debug(f"Truncated output: {len(text)} \u2192 {max_chars} (omitted {omitted})")
    return f"{text[:max_chars]}\n[Tool output truncated: omitted {omitted} chars]"
