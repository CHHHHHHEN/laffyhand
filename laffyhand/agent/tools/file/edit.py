import re
from pathlib import Path
from typing import Any

from loguru import logger
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.file._diff import format_diff
from laffyhand.agent.tools.file._fuzzy import (
    STRATEGIES,
    count_diff,
    find_all_fuzzy,
)
from laffyhand.agent.tools.file._security import (
    atomic_write,
    blocked_write_path,
)
from laffyhand.agent.tools.file._text_utils import (
    detect_line_ending,
    normalize_newlines,
)


class EditTool(BaseTool):
    name = "edit"
    path_params = ["file_path"]
    description = (
        "Perform a string replacement in a file. Supports exact match, "
        "fuzzy multi-line block matching, whitespace-normalized matching, "
        "and regex-based replacement.\n\n"
        "Use **old_string** for literal text replacement (with fuzzy fallback). "
        "Use **old_pattern** for regex-based replacement. "
        "When **replaceAll** is true, all matching occurrences are replaced "
        "(supports both exact and fuzzy matching)."
    )

    def _input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file to modify",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text to find and replace (use with or without old_pattern)",
                },
                "old_pattern": {
                    "type": "string",
                    "description": "Regex pattern to match against file content (alternative to old_string)",
                },
                "new_string": {
                    "type": "string",
                    "description": "The text to replace matches with (supports \\1 backreferences when old_pattern is used)",
                },
                "replaceAll": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default false). Works with both old_string and old_pattern.",
                },
            },
            "anyOf": [
                {"required": ["file_path", "old_string", "new_string"]},
                {"required": ["file_path", "old_pattern", "new_string"]},
            ],
        }

    async def run(self, params: dict[str, Any]) -> str:
        raw = params["file_path"]
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()
        old = params.get("old_string", "")
        new = params["new_string"]
        replace_all = params.get("replaceAll", False)
        old_pattern = params.get("old_pattern")

        block_reason = blocked_write_path(path)
        if block_reason:
            return f"Blocked: {block_reason}: {path}"

        if not path.exists():
            if not old and not old_pattern:
                return await self._create_file(path, new)
            return f"File not found: {path}"

        if path.is_dir():
            return f"Cannot edit a directory: {path}"

        content = path.read_text(encoding="utf-8")

        # Regex mode
        if old_pattern:
            return await self._replace_regex(path, content, old_pattern, new, replace_all)

        if not old:
            return await self._prepend_to_file(path, content, new)

        if replace_all:
            return await self._replace_all(path, content, old, new)

        return await self._replace_one(path, content, old, new)

    def _append_diff(self, result: str, path: Path, old_content: str, new_content: str) -> str:
        diff_display = format_diff(path, old_content, new_content)
        if diff_display.strip():
            result += f"\n\n{diff_display}"
        return result

    async def _create_file(self, path: Path, content: str) -> str:
        atomic_write(path, content)
        logger.info(f"Edit: created {path}")
        return f"Created {path} ({len(content)} chars)"

    async def _prepend_to_file(self, path: Path, content: str, prefix: str) -> str:
        line_ending = detect_line_ending(path)
        new_content = prefix + "\n" + content
        new_content = normalize_newlines(new_content, line_ending)
        atomic_write(path, new_content)
        logger.info(f"Edit: prepended to {path}")
        additions, deletions = count_diff("", prefix)
        result = f"Edited {path}: prepended (+{additions} lines)"
        return self._append_diff(result, path, content, new_content)

    async def _replace_regex(self, path: Path, content: str, pattern: str, new: str, replace_all: bool) -> str:
        line_ending = detect_line_ending(path)
        try:
            compiled = re.compile(pattern)
        except re.error as e:
            return f"Invalid regex pattern: {e}"

        matches = list(compiled.finditer(content))
        if not matches:
            return f"Pattern not found in {path}: {pattern}"

        if replace_all:
            new_content = compiled.sub(new, content)
            count = len(matches)
        else:
            new_content = compiled.sub(new, content, count=1)
            count = 1

        new_content = normalize_newlines(new_content, line_ending)
        atomic_write(path, new_content)
        additions, deletions = count_diff(
            content if count == 1 else matches[0].group(), new
        )
        logger.info(f"Edit: regex replaced {count} occurrence(s) in {path}")
        result = f"Edited {path} (regex): replaced {count} occurrence(s) (+{additions} lines, -{deletions} lines)"
        return self._append_diff(result, path, content, new_content)

    async def _replace_all(self, path: Path, content: str, old: str, new: str) -> str:
        line_ending = detect_line_ending(path)

        exact_count = content.count(old)
        fuzzy_matches = find_all_fuzzy(content, old)

        # Fast exact path — only when all matches are exact
        if exact_count > 0 and len(fuzzy_matches) == exact_count:
            new_content = content.replace(old, new)
            new_content = normalize_newlines(new_content, line_ending)
            atomic_write(path, new_content)
            additions, deletions = count_diff(old, new)
            logger.info(f"Edit: replaced {exact_count} occurrence(s) in {path}")
            result = f"Edited {path}: replaced {exact_count} occurrence(s) (+{additions} lines, -{deletions} lines)"
            return self._append_diff(result, path, content, new_content)

        # Fuzzy path — find all occurrences via fuzzy strategies
        if not fuzzy_matches:
            return f"old_string not found in {path}"

        # Replace in reverse order to preserve indices
        new_content = content
        for start, end in reversed(fuzzy_matches):
            new_content = new_content[:start] + new + new_content[end:]
        new_content = normalize_newlines(new_content, line_ending)
        atomic_write(path, new_content)
        additions, deletions = count_diff(old, new)
        label = "fuzzy" if exact_count == 0 else "mixed"
        logger.info(
            f"Edit: {label} replaced {len(fuzzy_matches)} occurrence(s) in {path}"
        )
        result = (
            f"Edited {path} ({label}): replaced {len(fuzzy_matches)} occurrence(s) "
            f"(+{additions} lines, -{deletions} lines)"
        )
        return self._append_diff(result, path, content, new_content)

    async def _replace_one(self, path: Path, content: str, old: str, new: str) -> str:
        line_ending = detect_line_ending(path)

        for name, match_fn in STRATEGIES:
            match = match_fn(content, old)
            if match is None:
                continue
            start, end = match
            matched_text = content[start:end]

            new_content = content[:start] + new + content[end:]
            new_content = normalize_newlines(new_content, line_ending)
            atomic_write(path, new_content)

            additions, deletions = count_diff(old, new)
            strategy = "exact" if matched_text == old else name
            logger.info(f"Edit: {strategy} match in {path}")
            result = (
                f"Edited {path} ({strategy} match): "
                f"replaced 1 occurrence (+{additions} lines, -{deletions} lines)"
            )
            return self._append_diff(result, path, content, new_content)

        return f"old_string not found in {path}"
