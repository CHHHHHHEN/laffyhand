import difflib
import re
from pathlib import Path
from typing import Any

from loguru import logger
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.file._fuzzy import STRATEGIES, count_diff
from laffyhand.agent.tools.file._security import (
    atomic_write,
    blocked_write_path,
    detect_line_ending,
    normalize_newlines,
)


class EditTool(BaseTool):
    name = "edit"
    description = "Perform an exact string replacement in a file."

    def _input_schema(self) -> dict:
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
        path = Path(params["file_path"])
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
        return f"Edited {path}: prepended (+{additions} lines)"

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
        return f"Edited {path}: replaced {count} occurrence(s) (+{additions} lines, -{deletions} lines)"

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
            return (
                f"Edited {path} ({strategy} match): "
                f"replaced 1 occurrence (+{additions} lines, -{deletions} lines)"
            )

        return f"old_string not found in {path}"
