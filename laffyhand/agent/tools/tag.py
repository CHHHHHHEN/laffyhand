from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from laffyhand.agent.db.repository.tag import FileTag
from laffyhand.agent.tools.base import BaseTool

if TYPE_CHECKING:
    from laffyhand.agent.db.repository.tag import FileTagRepo


_STALE_NOTE = (
    "Note: Tags are maintained by AI agents. "
    "Each file can have only one tag — "
    "use 'tag update' to modify it or 'tag add' to overwrite it. "
    "If this information is stale, run "
    "'tag update --file_path <path> --message <updated description>' to update it."
)


def _normalize(path_str: str) -> str:
    return os.path.realpath(path_str)


def _date_from_iso(iso: str) -> str:
    return iso[:10]


def _coerce_dict(value: Any) -> dict[str, str] | None:
    """Coerce a value to dict[str, str], parsing a JSON string if needed.

    LLMs sometimes send structured args like ``exports`` as a
    double-encoded JSON string (e.g. ``'{"ChatInput": "function"}'``)
    inside the outer JSON tool-call arguments.  This function
    normalises such values so downstream code always receives a dict.

    Returns ``None`` when *value* is ``None`` so callers can distinguish
    between "not provided" and "empty dict".
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return {k: str(v) for k, v in value.items()}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return {k: str(v) for k, v in parsed.items()}
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _coerce_list(value: Any) -> list[str] | None:
    """Coerce a value to list[str], parsing a JSON string if needed.

    Returns ``None`` when *value* is ``None`` so callers can distinguish
    between "not provided" and "empty list".
    """
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def format_tag_summary(tag: FileTag) -> str:
    date = _date_from_iso(tag.updated_at)
    stale = " ⚠️ STALE" if tag.status == "stale" else ""
    parts = [f"\U0001f516 {tag.message}"]
    if tag.exports:
        names = sorted(tag.exports.keys())
        parts.append(f"exports: {', '.join(names)}")
    if tag.side_effects:
        parts.append("side effects: yes")
    parts.append(f"({date}){stale}")
    return " ".join(parts)


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

    # Track current directory based on indentation (2 spaces per level)
    # Each entry: (indent_level, path)
    path_stack: list[tuple[int, Path]] = [(0, dir_path)]

    annotated: list[str] = []
    for line in lines:
        if line.startswith("  "):
            stripped = line.lstrip()
            indent = (len(line) - len(stripped)) // 2

            # Pop back to correct nesting parent
            while len(path_stack) > 1 and path_stack[-1][0] >= indent:
                path_stack.pop()

            entry_name = stripped.split(" ")[0]
            clean_name = entry_name.rstrip("/")

            if entry_name.endswith("/"):
                # Directory entry — push onto stack for subsequent children
                path_stack.append((indent, path_stack[-1][1] / clean_name))
                annotated.append(line)
            else:
                # File entry — resolve against the current directory path
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
        "Manage file tags — persistent semantic annotations for files that persist across sessions. "
        "Tags help you remember what a file does without re-reading it.\n\n"
        "Structured metadata fields:\n"
        "- exports: dict of exported symbol names mapped to their kind (class/function/constant/type/variable)\n"
        "- side_effects: free-text description of import-time side effects (empty = none)\n"
        "- depends_on: list of external module or file dependencies\n\n"
        "To hide tag annotations in glob/read output, pass show_tags=false to those tools.\n\n"
        "IMPORTANT: Each file path can have exactly ONE tag. "
        "A tag should be a holistic (macro-level) description of the file's overall purpose, "
        "not just what was changed in the most recent edit. "
        "For example, if a file implements authentication middleware, "
        "the tag should say 'Authentication middleware — validates JWTs and enforces RBAC', "
        "not 'Added JWT validation'.\n\n"
        "Choosing the right operation:\n"
        "- Use 'tag add' to create the first tag for a file, or to COMPLETELY OVERWRITE "
        "an existing tag with a new macro-level description.\n"
        "- Use 'tag update' to incrementally modify an existing tag (e.g. update the message, "
        "or add/change key-value metadata) without losing the rest.\n"
        "- If you are unsure whether a file already has a tag, "
        "call 'tag list --path <path>' first.\n\n"
        "Best practice — always tag files you create or modify:\n"
        "After you use write/edit to create or modify a file, call 'tag add' or 'tag batch' "
        "to annotate the file with a holistic description "
        "(what the file does overall, not just what was changed in this step). "
        "Similarly, after reading a file that lacks a tag or has a stale tag, "
        "update it so the knowledge persists across sessions. "
        "This maintains persistent context so you (and other agents) "
        "can understand the codebase without re-reading every file.\n\n"
        "Operations:\n"
        "- add --file_path <path> --message <description>: "
        "Tag a file with a macro-level semantic description. "
        "If the file already has a tag, this COMPLETELY OVERWRITES it. "
        "Use for first-time tagging or when the file's purpose has fundamentally changed.\n"
        "- update --file_path <path> --message <description>: "
        "Update the description of an existing tag without losing key-value metadata.\n"
        "- update --file_path <path> --key <k> --value <v>: "
        "Add or update a custom key-value field on an existing tag.\n"
        "- batch --tags <list>: Batch add/update multiple tags at once.\n"
        "- list [path]: List all tags (optionally under a directory). "
        "Use 'tag list --path <file>' to check if a file already has a tag.\n"
        "- prune [--delete]: Mark stale tags for missing files, or --delete to remove them permanently."
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
                    "description": "Macro-level semantic description of the file's overall purpose, not just what was changed",
                },
                "exports": {
                    "type": "object",
                    "description": "Exported symbols as a dict: {\"ClassName\": \"class\", \"func_name\": \"function\", \"CONST\": \"constant\"} (for add/update)",
                    "additionalProperties": {"type": "string"},
                },
                "side_effects": {
                    "type": "string",
                    "description": "Description of import-time side effects, e.g. 'registers signal handlers on import' (for add/update)",
                },
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of external module dependencies this file relies on (for add/update)",
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
                                "description": "Macro-level semantic description of the file's overall purpose",
                            },
                            "exports": {
                                "type": "object",
                                "description": "Exported symbols as a dict: {\"ClassName\": \"class\", \"func\": \"function\"}",
                                "additionalProperties": {"type": "string"},
                            },
                            "side_effects": {
                                "type": "string",
                                "description": "Description of import-time side effects",
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of external module dependencies",
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
        existing = self._repo.get(real)
        self._repo.upsert(
            real,
            message=message,
            status="active",
            exports=_coerce_dict(params.get("exports")),
            side_effects=params.get("side_effects"),
            depends_on=_coerce_list(params.get("depends_on")),
        )
        self._repo.commit()
        date = _date_from_iso(datetime.now(timezone.utc).isoformat())
        if existing:
            return (
                f"Tagged {real} (overwrote previous tag)\n"
                f"  Previous: \U0001f516 {existing.message}\n"
                f"  New:      \U0001f516 {message} ({date})\n"
                f"{_STALE_NOTE}"
            )
        return f"Tagged {real}\n\U0001f516 {message} ({date})\n{_STALE_NOTE}"

    def _update(self, params: dict[str, Any]) -> str:
        file_path = params.get("file_path")
        if not file_path:
            return "Error: --file_path is required for update"
        real = _normalize(file_path)
        if not os.path.exists(real):
            return f"Error: path does not exist: {file_path}"
        existing = self._repo.get(real)
        message = params.get("message")
        key = params.get("key")
        value = params.get("value")
        exports = _coerce_dict(params.get("exports"))
        side_effects = params.get("side_effects")
        depends_on = _coerce_list(params.get("depends_on"))
        has_structured = any(x is not None for x in (message, exports, side_effects, depends_on))
        if has_structured:
            self._repo.upsert(real, message=message, exports=exports, side_effects=side_effects, depends_on=depends_on)
        elif key is not None:
            self._repo.upsert(real, key=key, value=value)
        else:
            return "Error: provide --message, --exports/--side_effects/--depends_on, or --key/--value for update"
        self._repo.commit()
        tag = self._repo.get(real)
        assert tag is not None
        changes = []
        if existing:
            if message is not None and existing.message != message:
                changes.append(f"  message: {existing.message} → {message}")
            if key is not None:
                old_val = existing.tags.get(key, "(none)")
                changes.append(f"  {key}: {old_val} → {value or ''}")
            if exports is not None and existing.exports != exports:
                changes.append("  exports: updated")
            if side_effects is not None and existing.side_effects != side_effects:
                changes.append("  side_effects: updated")
            if depends_on is not None and existing.depends_on != depends_on:
                changes.append("  depends_on: updated")
        return f"Updated tag for {real}\n" + "\n".join(changes) + "\n" + _format_tag_detail(tag) + "\n" + _STALE_NOTE

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
                self._repo.upsert(
                    real,
                    message=message,
                    status="active",
                    exports=_coerce_dict(entry.get("exports")),
                    side_effects=entry.get("side_effects"),
                    depends_on=_coerce_list(entry.get("depends_on")),
                )
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
    stale = " \u26a0\ufe0f STALE (file no longer exists)" if tag.status == "stale" else ""
    lines.append(f"    \U0001f516 {tag.message} ({_date_from_iso(tag.updated_at)}){stale}")
    if tag.exports:
        lines.append("    exports:")
        for name, typ in tag.exports.items():
            lines.append(f"      {name}: {typ}")
    if tag.side_effects:
        lines.append(f"    side_effects: {tag.side_effects}")
    if tag.depends_on:
        lines.append("    depends_on:")
        for dep in tag.depends_on:
            lines.append(f"      {dep}")
    for k, v in tag.tags.items():
        lines.append(f"    {k}: {v}")
    return "\n".join(lines)
