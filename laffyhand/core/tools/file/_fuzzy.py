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


def _text_similarity(a: str, b: str) -> float:
    """Levenshtein-based similarity between 0 and 1."""
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 1.0
    distance = _levenshtein(a, b)
    return 1.0 - distance / max_len


def _levenshtein(s: str, t: str) -> int:
    """Classic Levenshtein distance."""
    if len(s) < len(t):
        s, t = t, s
    prev: list[int] = list(range(len(t) + 1))
    for sc in s:
        curr = [prev[0] + 1]
        for j, tc in enumerate(t):
            cost = 0 if sc == tc else 1
            curr.append(min(curr[-1] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


SINGLE_CANDIDATE_THRESHOLD = 0.3
MULTIPLE_CANDIDATES_THRESHOLD = 0.3


def block_anchor_match(content: str, old: str) -> tuple[int, int] | None:
    """Match multi-line blocks (>=3 lines) using first/last line anchors and
    Levenshtein similarity on middle lines.  Handles whitespace differences
    in anchor lines and moderate edits in middle lines."""
    lines = content.splitlines(keepends=True)
    old_lines_keeps = old.splitlines(keepends=True)
    old_lines = [ln.rstrip("\n\r") for ln in old_lines_keeps]

    if len(old_lines) < 3:
        return None

    first_raw = old_lines[0].strip()
    last_raw = old_lines[-1].strip()

    candidates: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() != first_raw:
            i += 1
            continue
        for j in range(i + 2, len(lines)):
            if lines[j].strip() == last_raw:
                candidates.append((i, j))
                break
        i += 1

    if not candidates:
        return None

    def _eval_candidate(start: int, end: int) -> float:
        middle = min(len(old_lines) - 2, end - start - 1)
        if middle <= 0:
            return 1.0
        total = 0.0
        for k in range(1, min(len(old_lines) - 1, end - start)):
            orig = lines[start + k].strip()
            search = old_lines[k].strip()
            total += _text_similarity(orig, search)
        return total / middle

    def _match_span(start: int, end: int) -> tuple[int, int]:
        """Compute character span without trailing newline of last line."""
        match_start = sum(len(lines[k]) for k in range(start))
        match_end = match_start + sum(
            len(lines[k]) for k in range(start, end)
        ) + len(lines[end].rstrip("\n\r"))
        return (match_start, match_end)

    # Single candidate — relaxed
    if len(candidates) == 1:
        start, end = candidates[0]
        sim = _eval_candidate(start, end)
        if sim >= SINGLE_CANDIDATE_THRESHOLD:
            return _match_span(start, end)
        return None

    # Multiple candidates — pick best
    best = max(candidates, key=lambda c: _eval_candidate(c[0], c[1]))
    start, end = best
    sim = _eval_candidate(start, end)
    if sim >= MULTIPLE_CANDIDATES_THRESHOLD:
        return _match_span(start, end)
    return None


def find_all_fuzzy(content: str, old: str) -> list[tuple[int, int]]:
    """Find all non-overlapping occurrences using fuzzy strategies.

    Returns the result from the strategy that finds the **most** matches
    (ties broken by strategy order = specificity).
    """
    best: list[tuple[int, int]] = []
    for _, match_fn in STRATEGIES:
        results: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        pos = 0
        while pos < len(content):
            m = match_fn(content[pos:], old)
            if m is None:
                break
            start, end = pos + m[0], pos + m[1]
            key = (start, end)
            if key not in seen and end > start:
                seen.add(key)
                results.append(key)
                pos = end if end > pos else pos + 1
            elif key in seen:
                pos = end
            else:
                pos += 1
        if results and len(results) >= len(best):
            if len(results) == len(best):
                continue  # first strategy wins ties (more specific)
            results.sort(key=lambda x: x[0])
            best = results
    return best


STRATEGIES: list[tuple[str, MatchFn]] = [
    ("exact", exact_match),
    ("whitespace normalized", whitespace_normalized_match),
    ("line trimmed", line_trimmed_match),
    ("block anchor", block_anchor_match),
    ("trimmed boundary", trimmed_boundary_match),
    ("escape normalized", escape_normalized_match),
]
