from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from loguru import logger

_DEFAULT_TRUNCATE = 2000


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
    logger.debug(f"Truncated output: {len(text)} → {max_chars} (omitted {omitted})")
    return f"{text[:max_chars]}\n[Tool output truncated: omitted {omitted} chars]"
