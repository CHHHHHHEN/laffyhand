"""Unified-diff formatting with configurable truncation.

Provides ``format_diff()`` which produces a unified-diff string between
two file versions, capped at a configurable line limit so that large
diffs are safe to display in LLM responses.
"""

import difflib
from pathlib import Path

from pydantic import BaseModel


# --- Models -------------------------------------------------------------------


class DiffConfig(BaseModel):
    """Controls how diffs are displayed."""
    max_lines: int = 50  # maximum lines to show before truncation


class DiffResult(BaseModel):
    """Structured result of a formatted diff."""
    display: str       # the formatted diff text (may be truncated)
    total_lines: int   # original number of lines before truncation
    truncated: bool    # whether the diff was truncated


# --- Implementation -----------------------------------------------------------


def _compute_diff(path: Path, old_content: str, new_content: str) -> str:
    """Generate raw unified diff between two file versions.

    Uses difflib.unified_diff with the file path as both fromfile and tofile.
    The returned diff is complete (no truncation) so that callers can
    decide how to handle long diffs.
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=str(path),
            tofile=str(path),
        )
    )


def format_diff(
    path: Path,
    old_content: str,
    new_content: str,
    config: DiffConfig | None = None,
) -> DiffResult:
    """Compute a truncated diff from old_content to new_content for display.

    Delegates to _compute_diff for the raw diff, then caps the output
    at config.max_lines. When truncated, appends a summary line indicating
    the total original line count so the caller knows how much was cut.
    """
    if config is None:
        config = DiffConfig()
    raw = _compute_diff(path, old_content, new_content)
    lines = raw.splitlines()
    total = len(lines)
    truncated = total > config.max_lines
    if truncated:
        lines = lines[: config.max_lines]
        lines.append(f"... diff truncated ({total} lines total)")
    return DiffResult(
        display="\n".join(lines),
        total_lines=total,
        truncated=truncated,
    )
