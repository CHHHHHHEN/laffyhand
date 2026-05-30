import glob as glob_module
import re
from pathlib import Path
from typing import Any

from loguru import logger
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.file._ripgrep import (
    rg_available, grep as rg_grep,
    grep_files as rg_grep_files, grep_count as rg_grep_count,
)

MAX_RESULTS = 100
MAX_LINE_LENGTH = 2000
MAX_FILE_SIZE = 1_000_000


class GrepTool(BaseTool):
    name = "grep"
    description = (
        "Search file contents using a regular expression. "
        "Results are sorted by file modification time (newest first) and limited to 100 matches. "
        "Uses ripgrep when available for significantly faster performance."
    )
    max_result_size = 100_000

    def _input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression to search for",
                },
                "include": {
                    "type": "string",
                    "description": "File glob filter (e.g. *.py, *.{ts,tsx})",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in (default: current working directory)",
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_only", "count"],
                    "description": "Output format: content (default), files_only (just file paths), count (per-file match counts)",
                },
                "context": {
                    "type": "integer",
                    "description": "Number of context lines before and after each match (default: 0)",
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip first N results for pagination (default: 0)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 100)",
                },
            },
            "required": ["pattern"],
        }

    async def run(self, params: dict[str, Any]) -> str:
        pattern_str = params["pattern"]
        include = params.get("include")
        output_mode = params.get("output_mode", "content")
        context = params.get("context", 0)
        offset = params.get("offset", 0)
        limit = params.get("limit", MAX_RESULTS)

        root = Path(params.get("path", "."))
        if not root.exists():
            return f"Path not found: {root}"

        if not pattern_str:
            return "Pattern is empty"

        try:
            re.compile(pattern_str)
        except re.error as e:
            return f"Invalid regex pattern: {e}"

        if root.is_file():
            return await self._search_single_file(root, pattern_str, context, offset, limit)

        return await self._search_directory(root, pattern_str, include, output_mode, context, offset, limit)

    async def _search_single_file(self, path: Path, pattern_str: str,
                                   context: int, offset: int, limit: int) -> str:
        if not path.is_file():
            return f"Not a file: {path}"
        if path.stat().st_size > MAX_FILE_SIZE:
            return f"Skipped (file too large): {path}"

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"{path}: error: {e}"

        pattern = re.compile(pattern_str)
        lines = text.splitlines(keepends=True)
        matches: list[str] = []
        for i, line in enumerate(lines):
            if pattern.search(line):
                display = line.rstrip("\n\r")
                if len(display) > MAX_LINE_LENGTH:
                    display = display[:MAX_LINE_LENGTH] + "... (truncated)"
                matches.append(f"{path}:{i + 1}: {display}")

        if not matches:
            return f"No matches for `{pattern_str}` in {path}"

        total = len(matches)
        selected = matches[offset:offset + limit] if offset else matches[:limit]
        result = "\n".join(selected)
        if len(selected) < total:
            result += f"\n[Showing {len(selected)} of {total} matches]"
        return result

    async def _search_directory(self, root: Path, pattern_str: str,
                                 include: str | None, output_mode: str,
                                 context: int, offset: int, limit: int) -> str:
        if output_mode == "files_only" and rg_available():
            result = self._rg_files_only(root, pattern_str, include, offset, limit)
            if result is not None:
                return result

        if output_mode == "count" and rg_available():
            result = self._rg_count(root, pattern_str, include, offset, limit)
            if result is not None:
                return result

        if output_mode == "content" and rg_available():
            result = self._rg_content(root, pattern_str, include, context, offset, limit)
            if result is not None:
                return result

        return self._py_search(root, pattern_str, include, output_mode, context, offset, limit)

    def _rg_files_only(self, root: Path, pattern_str: str,
                        include: str | None, offset: int, limit: int) -> str | None:
        results = rg_grep_files(root, pattern_str, include)
        if results is None:
            return None

        total = len(results)
        selected = results[offset:offset + limit] if offset else results[:limit]
        if not selected:
            return f"No matches for `{pattern_str}`"
        result = "\n".join(selected)
        if len(selected) < total:
            result += f"\n[Showing {len(selected)} of {total} files]"
        return result

    def _rg_count(self, root: Path, pattern_str: str,
                   include: str | None, offset: int, limit: int) -> str | None:
        raw = rg_grep_count(root, pattern_str, include)
        if raw is None:
            return None

        lines = [l for l in raw.splitlines() if l.strip()]
        total = len(lines)
        selected = lines[offset:offset + limit] if offset else lines[:limit]
        if not selected:
            return f"No matches for `{pattern_str}`"
        result = "\n".join(selected)
        if len(selected) < total:
            result += f"\n[Showing {len(selected)} of {total} files]"
        return result

    def _rg_content(self, root: Path, pattern_str: str,
                     include: str | None, context: int,
                     offset: int, limit: int) -> str | None:
        raw = rg_grep(root, pattern_str, include, context)
        if raw is None:
            return None

        lines = raw.splitlines()
        total = len(lines)
        selected = lines[offset:offset + limit] if offset else lines[:limit]
        if not selected:
            return f"No matches for `{pattern_str}`"

        result_lines: list[str] = []
        for line in selected:
            display = line
            if len(display) > MAX_LINE_LENGTH:
                display = display[:MAX_LINE_LENGTH] + "... (truncated)"
            result_lines.append(display)

        result = "\n".join(result_lines)
        if len(selected) < total:
            result += f"\n[Showing {len(selected)} of {total} lines]"
        return result

    def _py_search(self, root: Path, pattern_str: str,
                    include: str | None, output_mode: str,
                    context: int, offset: int, limit: int) -> str:
        try:
            pattern = re.compile(pattern_str)
        except re.error as e:
            return f"Invalid regex pattern: {e}"

        include_glob = include or "*"
        matched_files = sorted(glob_module.glob(include_glob, root_dir=root, recursive=True))

        files_with_matches: list[tuple[Path, list[str]]] = []

        for rel_path in matched_files:
            fp = root / rel_path
            if not fp.is_file():
                continue
            if fp.stat().st_size > MAX_FILE_SIZE:
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            lines = text.splitlines(keepends=True)
            file_matches: list[str] = []
            for i, line in enumerate(lines):
                if pattern.search(line):
                    display = line.rstrip("\n\r")
                    if len(display) > MAX_LINE_LENGTH:
                        display = display[:MAX_LINE_LENGTH] + "... (truncated)"
                    file_matches.append(f"{rel_path}:{i + 1}: {display}")
                    if context:
                        for ci in range(max(0, i - context), i):
                            ctx_line = lines[ci].rstrip("\n\r")
                            if len(ctx_line) > MAX_LINE_LENGTH:
                                ctx_line = ctx_line[:MAX_LINE_LENGTH] + "... (truncated)"
                            file_matches.append(f"{rel_path}:{ci + 1}- {ctx_line}")
                        for ci in range(i + 1, min(len(lines), i + context + 1)):
                            ctx_line = lines[ci].rstrip("\n\r")
                            if len(ctx_line) > MAX_LINE_LENGTH:
                                ctx_line = ctx_line[:MAX_LINE_LENGTH] + "... (truncated)"
                            file_matches.append(f"{rel_path}:{ci + 1}- {ctx_line}")

            if file_matches:
                files_with_matches.append((fp, file_matches))

        if not files_with_matches:
            return f"No matches for `{pattern_str}`"

        files_with_matches.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)

        if output_mode == "files_only":
            paths = [str(f.relative_to(root)) for f, _ in files_with_matches]
            total = len(paths)
            selected = paths[offset:offset + limit] if offset else paths[:limit]
            if not selected:
                return f"No matches for `{pattern_str}`"
            result = "\n".join(selected)
            if len(selected) < total:
                result += f"\n[Showing {len(selected)} of {total} files]"
            return result

        if output_mode == "count":
            result_lines = [f"{f.relative_to(root)}: {len(m)}" for f, m in files_with_matches]
            total = len(result_lines)
            selected = result_lines[offset:offset + limit] if offset else result_lines[:limit]
            if not selected:
                return f"No matches for `{pattern_str}`"
            result = "\n".join(selected)
            if len(selected) < total:
                result += f"\n[Showing {len(selected)} of {total} files]"
            return result

        all_matches: list[str] = []
        for _, file_matches in files_with_matches:
            for m in file_matches:
                if len(m) > MAX_LINE_LENGTH:
                    m = m[:MAX_LINE_LENGTH] + "... (truncated)"
            all_matches.extend(file_matches)

        total = len(all_matches)
        selected = all_matches[offset:offset + limit] if offset else all_matches[:limit]
        if not selected:
            return f"No matches for `{pattern_str}`"
        result = "\n".join(selected)
        if len(selected) < total:
            result += f"\n[Showing {len(selected)} of {total} lines]"
        return result
