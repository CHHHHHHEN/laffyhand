import difflib
from pathlib import Path
from typing import Any

from loguru import logger
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.file._fuzzy import STRATEGIES, count_diff
from laffyhand.agent.tools.file._security import (
    atomic_write,
    blocked_write_path,
)
from laffyhand.agent.tools.file._text_utils import (
    detect_line_ending,
    normalize_newlines,
)

MAX_DIFF_LINES = 50


def _compute_diff(path: Path, old_content: str, new_content: str) -> str:
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


class EditTool(BaseTool):
    name = "edit"
    description = "Perform an exact string replacement in a file."

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
                    "description": "The text to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The text to replace it with (must be different from oldString)",
                },
                "replaceAll": {
                    "type": "boolean",
                    "description": "Replace all occurrences of oldString (default false)",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    async def run(self, params: dict[str, Any]) -> str:
        raw = params["file_path"]
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()
        old = params["old_string"]
        new = params["new_string"]
        replace_all = params.get("replaceAll", False)

        block_reason = blocked_write_path(path)
        if block_reason:
            return f"Blocked: {block_reason}: {path}"

        if not path.exists():
            if not old:
                return await self._create_file(path, new)
            return f"File not found: {path}"

        if path.is_dir():
            return f"Cannot edit a directory: {path}"

        content = path.read_text(encoding="utf-8")

        if not old:
            return await self._prepend_to_file(path, content, new)

        if replace_all:
            return await self._replace_all(path, content, old, new)

        return await self._replace_one(path, content, old, new)

    def _append_diff(self, result: str, path: Path, old_content: str, new_content: str) -> str:
        diff = _compute_diff(path, old_content, new_content)
        diff_lines = diff.splitlines()
        if len(diff_lines) > MAX_DIFF_LINES:
            diff_lines = diff_lines[:MAX_DIFF_LINES]
            diff_lines.append(
                f"... diff truncated ({len(diff.splitlines())} lines total)"
            )
        diff_display = "\n".join(diff_lines)
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

    async def _replace_all(self, path: Path, content: str, old: str, new: str) -> str:
        line_ending = detect_line_ending(path)
        count = content.count(old)
        if count == 0:
            return f"old_string not found in {path}"
        new_content = content.replace(old, new)
        new_content = normalize_newlines(new_content, line_ending)
        atomic_write(path, new_content)
        additions, deletions = count_diff(old, new)
        logger.info(f"Edit: replaced {count} occurrence(s) in {path}")
        result = f"Edited {path}: replaced {count} occurrence(s) (+{additions} lines, -{deletions} lines)"
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
