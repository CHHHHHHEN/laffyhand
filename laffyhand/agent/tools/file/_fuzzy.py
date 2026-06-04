import difflib
import re
from typing import Callable


def count_diff(old: str, new: str) -> tuple[int, int]:
    """Count lines added and removed between two strings using SequenceMatcher."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    additions = 0
    deletions = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            deletions += i2 - i1
            additions += j2 - j1
        elif tag == "delete":
            deletions += i2 - i1
        elif tag == "insert":
            additions += j2 - j1
    return additions, deletions


MatchFn = Callable[[str, str], tuple[int, int] | None]


def _build_whitespace_flexible_regex(old: str) -> re.Pattern[str]:
    """Build a regex where any whitespace sequence in old matches \\s+."""
    parts = re.split(r"(\s+)", old)
    pattern_parts: list[str] = []
    for p in parts:
        if re.fullmatch(r"\s+", p):
            pattern_parts.append(r"\s+")
        else:
            pattern_parts.append(re.escape(p))
    return re.compile("".join(pattern_parts))


def exact_match(content: str, old: str) -> tuple[int, int] | None:
    idx = content.find(old)
    if idx == -1:
        return None
    return (idx, idx + len(old))


def whitespace_normalized_match(content: str, old: str) -> tuple[int, int] | None:
    """Match allowing any whitespace differences."""
    pattern = _build_whitespace_flexible_regex(old)
    m = pattern.search(content)
    if m:
        return (m.start(), m.end())
    return None


def trimmed_boundary_match(content: str, old: str) -> tuple[int, int] | None:
    """Match after stripping leading/trailing whitespace from old."""
    trimmed = old.strip()
    if not trimmed or trimmed == old:
        return None
    return exact_match(content, trimmed)


def line_trimmed_match(content: str, old: str) -> tuple[int, int] | None:
    """Match with each line individually trimmed."""
    lines = old.splitlines(keepends=True)
    trimmed_lines = [line.strip() for line in lines]
    trimmed = "".join(trimmed_lines)
    if trimmed == old:
        return None
    return exact_match(content, trimmed)


def escape_normalized_match(content: str, old: str) -> tuple[int, int] | None:
    """Match after unescaping common escape sequences in old."""
    unescaped = old.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
    if unescaped == old:
        return None
    return exact_match(content, unescaped)


STRATEGIES: list[tuple[str, MatchFn]] = [
    ("exact", exact_match),
    ("whitespace normalized", whitespace_normalized_match),
    ("line trimmed", line_trimmed_match),
    ("trimmed boundary", trimmed_boundary_match),
    ("escape normalized", escape_normalized_match),
]
