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
_STALE_NOTE = (
    "Note: Tags are maintained by AI agents. "
    "If this information is stale, run "
    "'tag update --file_path <path> --message <updated description>' to update it."
)


def _normalize(path_str: str) -> str:
    return os.path.realpath(path_str)


def _date_from_iso(iso: str) -> str:
    return iso[:10]


def format_tag_summary(tag: FileTag) -> str:
    message = tag.message
    if len(message) > _TAG_DISPLAY_LEN:
        message = message[:_TAG_DISPLAY_LEN - 3] + "..."
    date = _date_from_iso(tag.updated_at)
    stale = " ⚠️ STALE" if tag.status == "stale" else ""
    return f"\U0001f516 {message} ({date}){stale}"


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
        "Best practice — always tag files you create or modify:\n"
        "After you use write/edit to create or modify a file, call 'tag add' or 'tag batch' "
        "to annotate the file with a brief semantic description "
        "(e.g. what the file does or what was changed). "
        "Similarly, after reading a file that lacks a tag or has a stale tag, "
        "update it so the knowledge persists across sessions. "
        "This maintains persistent context so you (and other agents) "
        "can understand the codebase without re-reading every file.\n\n"
        "Operations:\n"
        "- add --file_path <path> --message <description>: Tag a file with a semantic description.\n"
        "- update --file_path <path> --message <description>: Update the description.\n"
        "- update --file_path <path> --key <k> --value <v>: Add or update a custom key-value field.\n"
        "- batch --tags <list>: Batch add/update multiple tags at once.\n"
        "- list [path]: List all tags (optionally under a directory).\n"
        "- prune [--delete]: Mark stale tags for missing files, or --delete to remove them entirely."
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
                    "enum": ["add", "update", "batch", "list", "prune"],
                    "description": "Operation to perform",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path to tag (for add/update)",
                },
                "message": {
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
                "status": {
                    "type": "string",
                    "enum": ["active", "stale"],
                    "description": "Filter tags by status (for list operation)",
                },
                "tags": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Absolute path to the file",
                            },
                            "message": {
                                "type": "string",
                                "description": "Semantic description of the file",
                            },
                        },
                        "required": ["file_path", "message"],
                    },
                    "description": "List of tags for batch operation",
                },
                "delete": {
                    "type": "boolean",
                    "description": "When pruning, set to true to permanently delete stale tags instead of marking them",
                    "default": False,
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
        if op == "batch":
            return self._batch(params)
        if op == "list":
            return self._list(params)
        if op == "prune":
            delete_mode = params.get("delete", False)
            return self._prune(delete_mode=delete_mode)
        return f"Unknown operation: {op}"

    def _add(self, params: dict[str, Any]) -> str:
        file_path = params.get("file_path")
        message = params.get("message")
        if not file_path:
            return "Error: --file_path is required for add"
        if not message:
            return "Error: --message is required for add"
        real = _normalize(file_path)
        if not os.path.exists(real):
            return f"Error: path does not exist: {file_path}"
        # Reset stale status if re-tagging an existing file
        self._repo.upsert(real, message=message, status="active")
        self._repo.commit()
        date = _date_from_iso(datetime.now(timezone.utc).isoformat())
        return f"Tagged {real}\n\U0001f516 {message} ({date})\n{_STALE_NOTE}"

    def _update(self, params: dict[str, Any]) -> str:
        file_path = params.get("file_path")
        if not file_path:
            return "Error: --file_path is required for update"
        real = _normalize(file_path)
        if not os.path.exists(real):
            return f"Error: path does not exist: {file_path}"
        message = params.get("message")
        key = params.get("key")
        value = params.get("value")
        if message:
            self._repo.upsert(real, message=message)
        elif key is not None:
            self._repo.upsert(real, key=key, value=value)
        else:
            return "Error: provide either --message or --key/--value for update"
        self._repo.commit()
        tag = self._repo.get(real)
        assert tag is not None
        return f"Updated tag for {real}\n{_format_tag_detail(tag)}\n{_STALE_NOTE}"

    def _batch(self, params: dict[str, Any]) -> str:
        tags = params.get("tags", [])
        if not tags:
            return "Error: --tags list is required for batch operation"
        results: list[str] = []
        for entry in tags:
            file_path = entry.get("file_path")
            message = entry.get("message", "")
            if not file_path or not message:
                results.append(f"Skipped entry {entry}: file_path and message are required")
                continue
            real = _normalize(file_path)
            if os.path.exists(real):
                self._repo.upsert(real, message=message, status="active")
                self._repo.commit()
                date = _date_from_iso(datetime.now(timezone.utc).isoformat())
                results.append(f"  \U0001f516 {real}: {message} ({date})")
            else:
                results.append(f"  Skipped (path not found): {real}")
        summary = f"Batch processed {len(results)} tag(s):\n" + "\n".join(results)
        return f"{summary}\n{_STALE_NOTE}"

    def _list(self, params: dict[str, Any]) -> str:
        path_str = params.get("path")
        status_filter = params.get("status")
        if path_str:
            real = _normalize(path_str)
            if os.path.isfile(real):
                tag = self._repo.get(real)
                tags = [tag] if tag else []
            else:
                prefix = real + "/" if not real.endswith("/") else real
                tags = self._repo.list_by_prefix(prefix)
        elif status_filter:
            tags = self._repo.list_by_status(status_filter)
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

    def _prune(self, delete_mode: bool = False) -> str:
        if delete_mode:
            deleted = self._repo.delete_missing()
            self._repo.commit()
            if deleted == 0:
                return "No orphan tags to delete."
            return f"Permanently deleted {deleted} orphan tag(s) for files that no longer exist.\n{_STALE_NOTE}"
        else:
            marked = self._repo.mark_stale_missing()
            self._repo.commit()
            if marked == 0:
                return f"No tags to mark as stale.\n{_STALE_NOTE}"
            return (
                f"Marked {marked} tag(s) as stale (file no longer exists). "
                f"Use 'tag prune --delete true' to permanently remove them.\n{_STALE_NOTE}"
            )


def _format_tag_detail(tag: FileTag) -> str:
    lines = [f"  {tag.path}"]
    stale = " ⚠️ STALE (file no longer exists)" if tag.status == "stale" else ""
    lines.append(f"    \U0001f516 {tag.message} ({_date_from_iso(tag.updated_at)}){stale}")
    for k, v in tag.tags.items():
        lines.append(f"    {k}: {v}")
    return "\n".join(lines)
