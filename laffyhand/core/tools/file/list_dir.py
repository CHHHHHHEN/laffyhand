"""List directory tool — show directory contents with depth control.

Supports .gitignore filtering, pagination, and line counts
for text files. Binary files are marked.
"""

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field
from laffyhand.core.tools.base import BaseTool
from laffyhand.core.tools.file._gitignore import GitignoreFilter
from laffyhand.core.tools.file._security import looks_binary


class ListDirParams(BaseModel):
    directory_path: str = Field(description="Absolute path to a directory to list")
    depth: int | None = Field(
        None,
        description="Directory listing depth. 1 = flat, 2 = one level deep (default), etc.",
    )
    offset: int | None = Field(
        None, description="Entry number to start from (1-indexed)"
    )
    limit: int | None = Field(
        None, description="Maximum number of top-level entries to return"
    )
    include_ignored: bool | None = Field(
        default=False,
        description="If true, include files that match .gitignore patterns (default: false)",
    )


class ListDirTool(BaseTool):
    name = "list_dir"
    path_params = ["directory_path"]
    description = (
        "List a directory's contents with line counts and binary detection.\n\n"
        "**Required:** ``directory_path``.\n\n"
        "Use ``depth`` to control recursion (default 2, 0 = nothing). "
        "Use ``offset`` (1-indexed) and ``limit`` to paginate top-level entries.\n\n"
        "``.gitignore`` is respected by default; ``include_ignored`` overrides it."
    )
    max_result_size = 50000

    def _input_schema(self) -> dict[str, Any]:
        return ListDirParams.model_json_schema()

    def _format_entry(
        self,
        entry: Path,
        indent: int,
        depth: int,
        gitignore: GitignoreFilter | None = None,
    ) -> list[str]:
        prefix = "  " * indent
        lines: list[str] = []

        if entry.is_dir():
            lines.append(f"{prefix}{entry.name}/")
        elif entry.is_file():
            if not looks_binary(entry):
                try:
                    text = entry.read_text(encoding="utf-8", errors="replace")
                    count = len(text.splitlines())
                    lines.append(f"{prefix}{entry.name} ({count} lines)")
                except Exception:
                    lines.append(f"{prefix}{entry.name}")
            else:
                lines.append(f"{prefix}{entry.name} (binary)")
        else:
            lines.append(f"{prefix}{entry.name}")

        if depth > 1 and entry.is_dir():
            try:
                children = sorted(
                    entry.iterdir(),
                    key=lambda p: (0 if p.is_dir() else 1, p.name.lower()),
                )
            except PermissionError:
                lines.append(f"{prefix}  (Permission denied)")
            else:
                for child in children:
                    if gitignore and gitignore.is_ignored(child):
                        continue
                    lines.extend(
                        self._format_entry(child, indent + 1, depth - 1, gitignore)
                    )

        return lines

    def _list_directory(
        self,
        path: Path,
        offset: int | None,
        limit: int | None,
        depth: int = 2,
        include_ignored: bool = False,
    ) -> str:
        if depth <= 0:
            return ""

        try:
            entries = sorted(
                path.iterdir(), key=lambda p: (0 if p.is_dir() else 1, p.name.lower())
            )
        except PermissionError:
            return f"Permission denied: {path}"

        gitignore = None if include_ignored else GitignoreFilter(path)

        if gitignore:
            entries = [e for e in entries if not gitignore.is_ignored(e)]

        total = len(entries)
        start = (offset - 1) if offset is not None else 0
        if offset is not None and offset > total:
            return f"Offset {offset} is out of range (directory has {total} entries)"
        end = total if limit is None else start + limit
        selected = entries[start:end]

        lines: list[str] = []
        lines.append(f"Contents of {path} (depth={depth}):")

        for entry in selected:
            lines.extend(self._format_entry(entry, 1, depth, gitignore))

        return "\n".join(lines)

    async def run(self, params: dict[str, Any]) -> str:
        directory_path: str | None = params.get("directory_path")

        if not directory_path:
            return "directory_path is required"

        path = Path(directory_path.strip())

        exists = await asyncio.to_thread(path.exists)
        if not exists:
            return f"Directory not found: {path}"

        is_dir = await asyncio.to_thread(path.is_dir)
        if not is_dir:
            return f"'{path}' is not a directory. Use the read tool to read files."

        logger.info(f"ListDir: listing directory {path}")
        result = await asyncio.to_thread(
            self._list_directory,
            path,
            params.get("offset"),
            params.get("limit"),
            params.get("depth", 2),
            params.get("include_ignored", False),
        )
        return result
