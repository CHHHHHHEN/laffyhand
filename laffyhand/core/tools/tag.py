"""Tag tool — annotate files with persistent semantic descriptions.

Operations: add, update, batch, list.
Tags persist across sessions and are shown in glob/read/list_dir output.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from laffyhand.core.db.models import FileTag
from laffyhand.core.tools.base import BaseTool


class TagBatchItem(BaseModel):
    file_path: str = Field(description="Absolute path to the file or directory")
    content: str = Field(
        description="Semantic description of the file's purpose"
    )


class TagParams(BaseModel):
    operation: str = Field(description="Operation to perform: add, update, batch, list")
    file_path: str | None = Field(
        None, description="File or directory path to tag (for add/update)"
    )
    content: str | None = Field(
        None,
        description="Semantic description of the file's overall purpose",
    )
    path: str | None = Field(
        None, description="Path (file or directory) to list or filter by"
    )
    tags: list[TagBatchItem] | None = Field(
        None, description="List of tags for batch operation"
    )


if TYPE_CHECKING:
    from laffyhand.core.db.repository.tag import FileTagRepo


_STALE_NOTE = (
    "Note: Tags are maintained by AI agents. "
    "Each file or directory can have only one tag. "
    "Use 'tag add' (first-time or major update) or 'tag update' (incremental). "
    "If this information is stale, run "
    "'tag update --file_path <path> --content <updated description>' to update it."
)


def _normalize(path_str: str) -> str:
    return os.path.realpath(path_str)


def _date_from_iso(iso: str) -> str:
    return iso[:10]


def format_tag_summary(tag: FileTag) -> str:
    date = _date_from_iso(tag.updated_at)
    return f"\U0001f516 {tag.content} ({date})"


def annotate_result(
    tool_name: str,
    result: str,
    params: dict[str, Any],
    repo: FileTagRepo,
) -> str:
    if not result:
        return result
    if not params.get("show_tags", True):
        return result
    if tool_name == "glob":
        return _annotate_glob(result, params, repo)
    if tool_name == "list_dir":
        return _annotate_read(result, params, repo)
    return result


def _annotate_glob(result: str, params: dict[str, Any], repo: FileTagRepo) -> str:
    root = Path(params.get("path", ".")).resolve()
    lines = result.splitlines(keepends=False)
    annotated: list[str] = []
    for line in lines:
        if not line or line.startswith("["):
            annotated.append(line)
            continue
        resolved = (
            Path(line).resolve() if line.startswith("/") else (root / line).resolve()
        )
        tag = repo.get(str(resolved))
        if tag:
            annotated.append(f"{line} {format_tag_summary(tag)}")
        else:
            annotated.append(line)
    return "\n".join(annotated)


def _annotate_read(result: str, params: dict[str, Any], repo: FileTagRepo) -> str:
    file_path = params.get("file_path") or params.get("directory_path")
    if not file_path or not result.startswith("Contents of "):
        return result
    dir_path = Path(file_path).resolve()
    lines = result.splitlines(keepends=False)

    path_stack: list[tuple[int, Path]] = [(0, dir_path)]

    annotated: list[str] = []
    for line in lines:
        if line.startswith("  "):
            stripped = line.lstrip()
            indent = (len(line) - len(stripped)) // 2

            while len(path_stack) > 1 and path_stack[-1][0] >= indent:
                path_stack.pop()

            entry_name = stripped.split(" ")[0]
            clean_name = entry_name.rstrip("/")

            if entry_name.endswith("/"):
                dir_path = path_stack[-1][1] / clean_name
                path_stack.append((indent, dir_path))
                tag = repo.get(str(dir_path))
                if tag:
                    annotated.append(f"{line} {format_tag_summary(tag)}")
                else:
                    annotated.append(line)
            else:
                full_path = path_stack[-1][1] / clean_name
                tag = repo.get(str(full_path))
                if tag:
                    annotated.append(f"{line} {format_tag_summary(tag)}")
                else:
                    annotated.append(line)
        else:
            annotated.append(line)
    return "\n".join(annotated)


class TagTool(BaseTool):
    name = "tag"
    description = (
        "Annotate files with persistent semantic descriptions.\n\n"
        "**Operations** (``operation`` parameter):\n"
        "  - ``add`` — tag a file (requires ``file_path`` + ``content``).\n"
        "  - ``update`` — change an existing tag's content.\n"
        "  - ``batch`` — add/update multiple files at once (``tags`` array).\n"
        "  - ``list`` — show tags (optionally filter by ``path``).\n\n"
        "Each file or directory path can have exactly ONE tag. "
        "Use holistic descriptions of the item's overall purpose, "
        "not just what changed in the last edit.\n\n"
        "Tags appear in glob/read/list_dir output; pass ``show_tags=false`` "
        "to those tools to hide annotations."
    )
    max_result_size = 50000

    def __init__(self, repo: FileTagRepo) -> None:
        super().__init__()
        self._repo = repo

    _TAG_SCHEMA: dict[str, Any] | None = None

    def _input_schema(self) -> dict[str, Any]:
        if TagTool._TAG_SCHEMA is not None:
            return TagTool._TAG_SCHEMA
        schema = TagParams.model_json_schema()
        schema.pop("title", None)
        schema.pop("$defs", None)
        schema["properties"]["operation"]["enum"] = [
            "add",
            "update",
            "batch",
            "list",
        ]
        TagTool._TAG_SCHEMA = schema
        return schema

    async def run(self, params: dict[str, Any]) -> str:
        op = params.get("operation")
        if op == "add":
            return self._add(params)
        if op == "update":
            return self._update(params)
        if op == "batch":
            return self._batch(params)
        if op == "list":
            return self._list(params)
        return f"Unknown operation: {op}"

    def _add(self, params: dict[str, Any]) -> str:
        file_path = params.get("file_path")
        content = params.get("content")
        if not file_path:
            return "Error: --file_path is required for add"
        if not content:
            return "Error: --content is required for add"
        real = _normalize(file_path)
        if not os.path.exists(real):
            return f"Error: path does not exist: {file_path}"
        existing = self._repo.get(real)
        self._repo.upsert(real, content=content)
        self._repo.commit()
        date = _date_from_iso(datetime.now(timezone.utc).isoformat())
        if existing:
            return (
                f"Tagged {real} (updated existing tag)\n"
                f"  content: {existing.content} \u2192 {content}\n"
                f"{_STALE_NOTE}"
            )
        return f"Tagged {real}\n\U0001f516 {content} ({date})\n{_STALE_NOTE}"

    def _update(self, params: dict[str, Any]) -> str:
        file_path = params.get("file_path")
        if not file_path:
            return "Error: --file_path is required for update"
        real = _normalize(file_path)
        if not os.path.exists(real):
            return f"Error: path does not exist: {file_path}"
        content = params.get("content")
        if not content:
            return "Error: --content is required for update"
        existing = self._repo.get(real)
        self._repo.upsert(real, content=content)
        self._repo.commit()
        tag = self._repo.get(real)
        assert tag is not None
        changes = []
        if existing and content is not None and existing.content != content:
            changes.append(f"  content: {existing.content} \u2192 {content}")
        return (
            f"Updated tag for {real}\n"
            + "\n".join(changes)
            + "\n"
            + _format_tag_detail(tag)
            + "\n"
            + _STALE_NOTE
        )

    def _batch(self, params: dict[str, Any]) -> str:
        tags = params.get("tags", [])
        if not tags:
            return "Error: --tags list is required for batch operation"
        results: list[str] = []
        for entry in tags:
            file_path = entry.get("file_path")
            content = entry.get("content", "")
            if not file_path or not content:
                results.append(
                    f"Skipped entry {entry}: file_path and content are required"
                )
                continue
            real = _normalize(file_path)
            if os.path.exists(real):
                self._repo.upsert(real, content=content)
                self._repo.commit()
                date = _date_from_iso(datetime.now(timezone.utc).isoformat())
                results.append(f"  \U0001f516 {real}: {content} ({date})")
            else:
                results.append(f"  Skipped (path not found): {real}")
        summary = f"Batch processed {len(results)} tag(s):\n" + "\n".join(results)
        return f"{summary}\n{_STALE_NOTE}"

    def _list(self, params: dict[str, Any]) -> str:
        path_str = params.get("path")
        if path_str:
            real = _normalize(path_str)
            if os.path.isfile(real):
                tag = self._repo.get(real)
                tags = [tag] if tag else []
            elif os.path.isdir(real):
                dir_tag = self._repo.get(real)
                prefix = os.path.join(real, "") if not real.endswith(os.sep) else real
                children = self._repo.list_by_prefix(prefix)
                tags = ([dir_tag] if dir_tag else []) + children
            else:
                prefix = os.path.join(real, "") if not real.endswith(os.sep) else real
                tags = self._repo.list_by_prefix(prefix)
        else:
            tags = self._repo.list_all()
        if not tags:
            return "No tags found."
        parts = [f"Found {len(tags)} tag(s):"]
        for tag in tags:
            parts.append("")
            parts.append(_format_tag_detail(tag))
        parts.append("")
        parts.append(_STALE_NOTE)
        return "\n".join(parts)


def _format_tag_detail(tag: FileTag) -> str:
    lines = [f"  {tag.path}"]
    lines.append(
        f"    \U0001f516 {tag.content} ({_date_from_iso(tag.updated_at)})"
    )
    return "\n".join(lines)
