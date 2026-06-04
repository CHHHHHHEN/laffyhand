from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from laffyhand.agent.db.repository.tag import FileTag
from laffyhand.agent.tools.base import BaseTool

if TYPE_CHECKING:
    from laffyhand.agent.db.repository.tag import FileTagRepo


_TAG_DISPLAY_LEN = 60


def _normalize(path_str: str) -> str:
    return os.path.realpath(path_str)


def _date_from_iso(iso: str) -> str:
    return iso[:10]


def format_tag_summary(tag: FileTag) -> str:
    message = tag.message
    if len(message) > _TAG_DISPLAY_LEN:
        message = message[:_TAG_DISPLAY_LEN - 3] + "..."
    date = _date_from_iso(tag.updated_at)
    return f"\U0001f516 {message} ({date})"


def annotate_result(
    tool_name: str,
    result: str,
    params: dict[str, Any],
    repo: FileTagRepo,
) -> str:
    if not result:
        return result
    if tool_name == "glob":
        return _annotate_glob(result, params, repo)
    if tool_name == "read":
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
        resolved = Path(line).resolve() if line.startswith("/") else (root / line).resolve()
        tag = repo.get(str(resolved))
        if tag:
            annotated.append(f"{line} {format_tag_summary(tag)}")
        else:
            annotated.append(line)
    return "\n".join(annotated)


def _annotate_read(result: str, params: dict[str, Any], repo: FileTagRepo) -> str:
    file_path = params.get("file_path")
    if not file_path or not result.startswith("Contents of "):
        return result
    dir_path = Path(file_path).resolve()
    lines = result.splitlines(keepends=False)
    annotated: list[str] = []
    for line in lines:
        if line.startswith("  "):
            name = line.lstrip().split(" ")[0].rstrip("/")
            full_path = dir_path / name
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
        "Manage file tags — persistent semantic annotations for files that persist across sessions. "
        "Tags help you remember what a file does without re-reading it.\n\n"
        "Operations:\n"
        "- add --file <path> --msg <description>: Tag a file with a semantic description.\n"
        "- update --file <path> --msg <description>: Update the description.\n"
        "- update --file <path> --key <k> --value <v>: Add or update a custom key-value field.\n"
        "- list [path]: List all tags (optionally under a directory).\n"
        "- prune: Remove tags for files that no longer exist."
    )
    max_result_size = 50000

    def __init__(self, repo: FileTagRepo) -> None:
        super().__init__()
        self._repo = repo

    def _input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["add", "update", "list", "prune"],
                    "description": "Operation to perform",
                },
                "file": {
                    "type": "string",
                    "description": "File path to tag",
                },
                "msg": {
                    "type": "string",
                    "description": "Semantic description of the file",
                },
                "key": {
                    "type": "string",
                    "description": "Custom key for key-value pair (use with --value)",
                },
                "value": {
                    "type": "string",
                    "description": "Value for the custom key (use with --key)",
                },
                "path": {
                    "type": "string",
                    "description": "Directory path to list or filter by",
                },
            },
            "required": ["operation"],
        }

    async def run(self, params: dict[str, Any]) -> str:
        op = params.get("operation")
        if op == "add":
            return self._add(params)
        if op == "update":
            return self._update(params)
        if op == "list":
            return self._list(params)
        if op == "prune":
            return self._prune()
        return f"Unknown operation: {op}"

    def _add(self, params: dict[str, Any]) -> str:
        file_path = params.get("file")
        msg = params.get("msg")
        if not file_path:
            return "Error: --file is required for add"
        if not msg:
            return "Error: --msg is required for add"
        real = _normalize(file_path)
        if not os.path.exists(real):
            return f"Error: path does not exist: {file_path}"
        self._repo.upsert(real, message=msg)
        self._repo.commit()
        date = _date_from_iso(datetime.now(timezone.utc).isoformat())
        return f"Tagged {real}\n\U0001f516 {msg} ({date})"

    def _update(self, params: dict[str, Any]) -> str:
        file_path = params.get("file")
        if not file_path:
            return "Error: --file is required for update"
        real = _normalize(file_path)
        if not os.path.exists(real):
            return f"Error: path does not exist: {file_path}"
        msg = params.get("msg")
        key = params.get("key")
        value = params.get("value")
        if msg:
            self._repo.upsert(real, message=msg)
        elif key is not None:
            self._repo.upsert(real, key=key, value=value)
        else:
            return "Error: provide either --msg or --key/--value for update"
        self._repo.commit()
        tag = self._repo.get(real)
        assert tag is not None
        return f"Updated tag for {real}\n{_format_tag_detail(tag)}"

    def _list(self, params: dict[str, Any]) -> str:
        path_str = params.get("path")
        if path_str:
            real = _normalize(path_str)
            if os.path.isfile(real):
                tag = self._repo.get(real)
                tags = [tag] if tag else []
            else:
                prefix = real + "/" if not real.endswith("/") else real
                tags = self._repo.list_by_prefix(prefix)
        else:
            tags = self._repo.list_all()
        if not tags:
            return "No tags found."
        parts = [f"Found {len(tags)} tag(s):"]
        for tag in tags:
            parts.append("")
            parts.append(_format_tag_detail(tag))
        return "\n".join(parts)

    def _prune(self) -> str:
        deleted = self._repo.delete_missing()
        self._repo.commit()
        if deleted == 0:
            return "No orphan tags to prune."
        return f"Pruned {deleted} orphan tag(s) for files that no longer exist."


def _format_tag_detail(tag: FileTag) -> str:
    lines = [f"  {tag.path}"]
    lines.append(f"    \U0001f516 {tag.message} ({_date_from_iso(tag.updated_at)})")
    for k, v in tag.tags.items():
        lines.append(f"    {k}: {v}")
    return "\n".join(lines)
