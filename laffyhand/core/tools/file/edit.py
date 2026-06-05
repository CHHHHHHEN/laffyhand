"""Edit tool — replace text in an existing file via ``changes`` array.

Each change item needs ``new_string`` plus ``old_string``
(literal match) or ``old_pattern`` (regex).
"""

import re
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field, ValidationError
from laffyhand.core.tools.base import BaseTool
from laffyhand.core.tools.file._diff import format_diff
from laffyhand.core.tools.file._fuzzy import (
    STRATEGIES,
    find_all_fuzzy,
)
from laffyhand.core.tools.file._security import (
    atomic_write,
    blocked_write_path,
)
from laffyhand.core.tools.file._text_utils import (
    detect_line_ending,
    normalize_newlines,
)


class ChangeParams(BaseModel):
    """One edit item — requires ``new_string`` plus ``old_string``
    (literal match) or ``old_pattern`` (regex)."""

    old_string: str | None = Field(None, description="Literal text to find. Provide either this or old_pattern.")
    old_pattern: str | None = Field(None, description="Regex pattern to find. Provide either this or old_string.")
    new_string: str = Field(description="Replacement text. Supports ``\\1`` backreferences with old_pattern.")
    replaceAll: bool | None = Field(default=False, description="Replace all occurrences (false = first match only)")


class EditParams(BaseModel):
    """Required: ``file_path`` (target file) + ``changes`` (one or more edits)."""

    file_path: str = Field(description="Path to the file to edit. Absolute path recommended; relative paths resolve from cwd.")
    changes: list[ChangeParams] = Field(description="Edits applied sequentially — each sees the previous change's result. Every item needs new_string + old_string or old_pattern.")


_EDIT_SCHEMA_CACHE: dict[str, Any] | None = None


def _edit_schema() -> dict[str, Any]:
    global _EDIT_SCHEMA_CACHE
    if _EDIT_SCHEMA_CACHE is not None:
        return _EDIT_SCHEMA_CACHE
    schema = EditParams.model_json_schema()
    schema.pop("title", None)
    # inject anyOf on each change item — Pydantic can't express
    # "old_string XOR old_pattern" natively
    items = schema["properties"]["changes"]["items"]
    items["anyOf"] = [
        {"required": ["new_string", "old_string"]},
        {"required": ["new_string", "old_pattern"]},
    ]
    _EDIT_SCHEMA_CACHE = schema
    return schema


class EditTool(BaseTool):
    name = "edit"
    path_params = ["file_path"]
    description = (
        "Replace text in an existing file.\n\n"
        "**Required:** ``file_path`` + ``changes`` (array).\n"
        "Each change item needs ``new_string`` plus either "
        "``old_string`` (literal match) or ``old_pattern`` (regex).\n\n"
        "Optional per-item: ``replaceAll`` (default false = first match only).\n\n"
        "Changes apply sequentially — item 2 sees the result of item 1. "
        "A unified diff is returned on success.\n\n"
        "The file must already exist (the tool does not create files). "
        "Blocked paths (e.g. ``.env``) are rejected."
    )

    def _input_schema(self) -> dict[str, Any]:
        return _edit_schema()

    async def run(self, params: dict[str, Any]) -> str:
        raw = params["file_path"]
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()

        block_reason = blocked_write_path(path)
        if block_reason:
            return f"Blocked: {block_reason}: {path}"

        return await self._apply_all(path, params["changes"])

    # --- Write + diff helper ---------------------------------------------------

    async def _write_and_report(
        self, path: Path, old_content: str, new_content: str, summary: str,
    ) -> str:
        """Write *new_content*, compute diff, and return a formatted result."""
        await atomic_write(path, new_content)
        diff_result = format_diff(path, old_content, new_content)
        result = f"{summary} (+{diff_result.additions} lines, -{diff_result.deletions} lines)"
        if diff_result.display.strip():
            result += f"\n\n{diff_result.display}"
        return result

    # --- Change application ----------------------------------------------------

    async def _apply_all(self, path: Path, changes: list[dict[str, Any]]) -> str:
        if not changes:
            return f"No changes provided for {path}"

        if not path.exists():
            return f"File not found: {path}"
        if path.is_dir():
            return f"Cannot edit a directory: {path}"

        content = path.read_text(encoding="utf-8", errors="replace")
        original = content

        for i, change_dict in enumerate(changes):
            try:
                change = ChangeParams.model_validate(change_dict)
            except ValidationError as e:
                missing = [f"'{err['loc'][0]}'" for err in e.errors() if err['type'] == 'missing']
                if missing:
                    return f"Change {i + 1}: {', '.join(missing)} is required"
                return f"Change {i + 1}: invalid parameters"
            old = change.old_string
            pattern = change.old_pattern

            if not old and not pattern:
                return f"Change {i + 1}: 'old_string' or 'old_pattern' is required"

            if pattern:
                try:
                    compiled = re.compile(pattern)
                except re.error as e:
                    return f"Change {i + 1}: invalid regex: {e}"
                matches = list(compiled.finditer(content))
                if not matches:
                    return f"Change {i + 1}: pattern not found: {pattern}"
                if change.replaceAll:
                    content = compiled.sub(change.new_string, content)
                else:
                    content = compiled.sub(change.new_string, content, count=1)
            elif change.replaceAll:
                assert old
                exact_count = content.count(old)
                fuzzy_matches = find_all_fuzzy(content, old)
                if not fuzzy_matches:
                    return f"Change {i + 1}: old_string not found: {old}"
                if exact_count > 0 and len(fuzzy_matches) == exact_count:
                    content = content.replace(old, change.new_string)
                else:
                    for start, end in reversed(fuzzy_matches):
                        content = content[:start] + change.new_string + content[end:]
            else:
                assert old
                matched = False
                for _name, match_fn in STRATEGIES:
                    match = match_fn(content, old)
                    if match is not None:
                        start, end = match
                        content = content[:start] + change.new_string + content[end:]
                        matched = True
                        break
                if not matched:
                    return f"Change {i + 1}: old_string not found: {old}"

        line_ending = detect_line_ending(path)
        content = normalize_newlines(content, line_ending)
        logger.info(f"Edit: applied {len(changes)} change(s) to {path}")
        return await self._write_and_report(path, original, content, f"Edited {path}: applied {len(changes)} change(s)")


