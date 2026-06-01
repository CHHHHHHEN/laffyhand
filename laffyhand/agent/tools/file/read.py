import difflib
from pathlib import Path
from typing import Any

from loguru import logger
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.file._security import looks_binary


MAX_CONSECUTIVE_READS = 4
MAX_CACHE_SIZE = 200


class ReadTool(BaseTool):
    name = "read"
    description = (
        "Read a file or directory from the local filesystem. "
        "If the path does not exist, an error is returned. "
        "The filePath parameter should be an absolute path. "
        "By default, this tool returns up to 2000 lines from the start of the file. "
        "The offset parameter is the line number to start from (1-indexed). "
        "Any line longer than 2000 characters is truncated."
    )
    max_result_size = 50000

    def __init__(self) -> None:
        self._read_cache: dict[str, tuple[float, str]] = {}
        self._consecutive: dict[str, int] = {}

    def _input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file or directory to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "The line number to start reading from (1-indexed)",
                },
                "limit": {
                    "type": "integer",
                    "description": "The maximum number of lines to read (defaults to 2000)",
                },
            },
            "required": ["file_path"],
        }

    def _cache_key(self, path: Path, offset: int | None, limit: int | None) -> str:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        return f"{resolved}:{offset or ''}:{limit or ''}"

    def _suggest_similar(self, path: Path) -> list[str]:
        if not path.parent.exists():
            return []
        try:
            candidates = [p.name for p in path.parent.iterdir() if p.is_file()]
        except PermissionError:
            return []
        return difflib.get_close_matches(path.name, candidates, n=5, cutoff=0.3)

    def _list_directory(self, path: Path, offset: int | None, limit: int | None) -> str:
        try:
            entries = sorted(
                path.iterdir(), key=lambda p: (0 if p.is_dir() else 1, p.name.lower())
            )
        except PermissionError:
            return f"Permission denied: {path}"
        total = len(entries)
        start = (offset - 1) if offset is not None else 0
        if offset is not None and offset > total:
            return f"Offset {offset} is out of range (directory has {total} entries)"
        end = total if limit is None else start + limit
        selected = entries[start:end]
        lines = [f"Contents of {path}:"]
        for entry in selected:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.name}{suffix}")
        return "\n".join(lines)

    async def run(self, params: dict[str, Any]) -> str:
        path = Path(params["file_path"])

        if not path.exists():
            msg = f"File not found: {path}"
            suggestions = self._suggest_similar(path)
            if suggestions:
                msg += "\nDid you mean?\n" + "\n".join(f"  {s}" for s in suggestions)
            return msg

        if path.is_dir():
            result = self._list_directory(
                path, params.get("offset"), params.get("limit")
            )
            logger.info(f"Read: listed directory {path}")
            return result

        if looks_binary(path):
            logger.info(f"Read: skipped binary file {path}")
            return f"File appears to be binary and cannot be read as text: {path}"

        offset = params.get("offset")
        limit = params.get("limit")
        key = self._cache_key(path, offset, limit)

        try:
            current_mtime = path.stat().st_mtime
        except OSError:
            current_mtime = 0.0

        # Dedup & consecutive-read guard
        if key in self._read_cache:
            cached_mtime, _ = self._read_cache[key]
            if cached_mtime == current_mtime:
                self._consecutive[key] = self._consecutive.get(key, 0) + 1
                count = self._consecutive[key]
                if count >= MAX_CONSECUTIVE_READS:
                    return (
                        f"File `{path}` has been read {count} times consecutively "
                        "without changes. Try a different approach."
                    )
                msg = "File unchanged since last read."
                if count > 1:
                    msg += f" (consecutive read #{count})"
                return msg

        # Reset consecutive counter when file changed or first read
        self._consecutive.pop(key, None)

        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines(keepends=True)
        total_lines = len(lines)

        if offset is not None and offset < 1:
            return f"Invalid offset: {offset}. Offset must be >= 1."
        if offset is not None and offset > total_lines:
            return f"Offset {offset} is out of range (file has {total_lines} lines)"

        start = (offset - 1) if offset is not None else 0
        end = total_lines if limit is None else start + limit
        selected = lines[start:end]

        line_num_width = max(4, len(str(total_lines)))
        result_parts: list[str] = []
        for i, line in enumerate(selected, start + 1):
            line_num = f"{i:>{line_num_width}d}"
            if len(line) > 2000:
                line = line[:2000]
                if line.endswith("\n"):
                    line = line[:-1]
                line += "... (line truncated to 2000 chars)\n"
            if not line.endswith("\n"):
                line += "\n"
            result_parts.append(f"{line_num}|{line}")

        result = "".join(result_parts)

        if offset is None and limit is None and len(text) > 512 * 1024:
            result += f"\n[File is large ({len(text)} bytes). Use offset and limit to read specific sections.]"

        logger.info(
            f"Read: {path} ({total_lines} lines, offset={offset}, limit={limit})"
        )
        self._read_cache[key] = (current_mtime, result)
        if len(self._read_cache) > MAX_CACHE_SIZE:
            oldest = next(iter(self._read_cache))
            del self._read_cache[oldest]

        return result
