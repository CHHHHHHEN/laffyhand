"""Unified-diff formatting with configurable truncation.

Provides ``format_diff()`` which produces a unified-diff string between
two file versions. By default the output is capped at ``max_lines`` so
that large diffs are safe to display in LLM responses; pass
``truncate=False`` on ``DiffConfig`` to disable truncation entirely.
"""

import difflib
from pathlib import Path

from pydantic import BaseModel, Field


# --- Models -------------------------------------------------------------------


class DiffConfig(BaseModel):
    """Controls how diffs are displayed."""

    max_lines: int = Field(default=50, description="Maximum lines to show before truncation")
    truncate: bool = Field(default=True, description="Set to False to disable truncation")


class DiffResult(BaseModel):
    """Structured result of a formatted diff."""

    display: str = Field(description="The formatted diff text (may be truncated)")
    total_lines: int = Field(description="Original number of lines before truncation")
    truncated: bool = Field(description="Whether the diff was truncated")
    additions: int = Field(description="Lines added")
    deletions: int = Field(description="Lines removed")


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


def _count_diff_lines(raw: str) -> tuple[int, int]:
    """Count +/- lines in a unified-diff string (excluding ---/+++ headers)."""
    additions = 0
    deletions = 0
    for line in raw.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


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
    additions, deletions = _count_diff_lines(raw)
    lines = raw.splitlines()
    total = len(lines)
    if config.truncate and total > config.max_lines:
        lines = lines[: config.max_lines]
        lines.append(f"... diff truncated ({total} lines total)")
        return DiffResult(
            display="\n".join(lines),
            total_lines=total,
            truncated=True,
            additions=additions,
            deletions=deletions,
        )
    return DiffResult(
        display="\n".join(lines),
        total_lines=total,
        truncated=False,
        additions=additions,
        deletions=deletions,
    )
