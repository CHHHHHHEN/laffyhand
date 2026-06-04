import difflib
from pathlib import Path


MAX_DIFF_LINES = 50


def compute_diff(path: Path, old_content: str, new_content: str) -> str:
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=str(path),
            tofile=str(path),
        )
    )
    return "".join(diff)


def format_diff(path: Path, old_content: str, new_content: str) -> str:
    """Compute diff and truncate to MAX_DIFF_LINES for display."""
    diff = compute_diff(path, old_content, new_content)
    diff_lines = diff.splitlines()
    if len(diff_lines) > MAX_DIFF_LINES:
        diff_lines = diff_lines[:MAX_DIFF_LINES]
        diff_lines.append(
            f"... diff truncated ({len(diff.splitlines())} lines total)"
        )
    return "\n".join(diff_lines)
