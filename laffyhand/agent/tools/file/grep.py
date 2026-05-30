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
            logger.info(f"Grep: skipped large file {path}")
            return f"Skipped (file too large): {path}"

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Grep: failed to read {path}: {e}")
            return f"{path}: error: {e}"

        pattern = re.compile(pattern_str)
        lines = text.splitlines(keepends=True)
        match_indices = [i for i, line in enumerate(lines) if pattern.search(line)]

        if not match_indices:
            logger.info(f"Grep: no matches for `{pattern_str}` in {path}")
            return f"No matches for `{pattern_str}` in {path}"

        total_matches = len(match_indices)
        selected_indices = match_indices[offset:offset + limit] if offset else match_indices[:limit]

        result_lines: list[str] = []
        for idx in selected_indices:
            display = lines[idx].rstrip("\n\r")
            if len(display) > MAX_LINE_LENGTH:
                display = display[:MAX_LINE_LENGTH] + "... (truncated)"
            result_lines.append(f"{path}:{idx + 1}: {display}")
            for ci in range(max(0, idx - context), idx):
                ctx = lines[ci].rstrip("\n\r")
                if len(ctx) > MAX_LINE_LENGTH:
                    ctx = ctx[:MAX_LINE_LENGTH] + "... (truncated)"
                result_lines.append(f"{path}:{ci + 1}- {ctx}")
            for ci in range(idx + 1, min(len(lines), idx + context + 1)):
                ctx = lines[ci].rstrip("\n\r")
                if len(ctx) > MAX_LINE_LENGTH:
                    ctx = ctx[:MAX_LINE_LENGTH] + "... (truncated)"
                result_lines.append(f"{path}:{ci + 1}- {ctx}")

        result = "\n".join(result_lines)
        if len(selected_indices) < total_matches:
            result += f"\n[Showing {len(selected_indices)} of {total_matches} matches]"
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

        if output_mode == "files_only":
            return self._py_search_files_only(root, pattern_str, include, offset, limit)
        if output_mode == "count":
            return self._py_search_count(root, pattern_str, include, offset, limit)
        return self._py_search_content(root, pattern_str, include, context, offset, limit)

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

        lines = [ln for ln in raw.splitlines() if ln.strip()]
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

    def _py_search_files_only(self, root: Path, pattern_str: str,
                               include: str | None, offset: int, limit: int) -> str:
        logger.debug(f"Grep: Python fallback files_only for `{pattern_str}` in {root}")
        files_with_matches = self._collect_matches(root, pattern_str, include)
        if not files_with_matches:
            return f"No matches for `{pattern_str}`"

        paths = [str(f.relative_to(root)) for f, _ in files_with_matches]
        total = len(paths)
        selected = paths[offset:offset + limit] if offset else paths[:limit]
        if not selected:
            return f"No matches for `{pattern_str}`"
        result = "\n".join(selected)
        if len(selected) < total:
            result += f"\n[Showing {len(selected)} of {total} files]"
        return result

    def _py_search_count(self, root: Path, pattern_str: str,
                           include: str | None, offset: int, limit: int) -> str:
        logger.debug(f"Grep: Python fallback count for `{pattern_str}` in {root}")
        files_with_matches = self._collect_matches(root, pattern_str, include)
        if not files_with_matches:
            return f"No matches for `{pattern_str}`"

        result_lines = [f"{f.relative_to(root)}: {len(m)}" for f, m in files_with_matches]
        total = len(result_lines)
        selected = result_lines[offset:offset + limit] if offset else result_lines[:limit]
        if not selected:
            return f"No matches for `{pattern_str}`"
        result = "\n".join(selected)
        if len(selected) < total:
            result += f"\n[Showing {len(selected)} of {total} files]"
        return result

    def _py_search_content(self, root: Path, pattern_str: str,
                            include: str | None, context: int,
                            offset: int, limit: int) -> str:
        logger.debug(f"Grep: Python fallback content for `{pattern_str}` in {root}")
        try:
            pattern = re.compile(pattern_str)
        except re.error as e:
            return f"Invalid regex pattern: {e}"

        include_glob = include or "*"
        matched_files = sorted(glob_module.glob(include_glob, root_dir=root, recursive=True))

        # Collect (file_path, [match_line_index, ...]) for each file
        file_match_indices: list[tuple[Path, list[int]]] = []
        lines_cache: dict[str, list[str]] = {}

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
            match_indices = [i for i, line in enumerate(lines) if pattern.search(line)]
            if match_indices:
                file_match_indices.append((fp, match_indices))
                lines_cache[str(fp)] = lines

        if not file_match_indices:
            return f"No matches for `{pattern_str}`"

        file_match_indices.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)

        # Build flat match list: (file_rel, line_index) pairs
        flat_matches: list[tuple[Path, int]] = []
        for fp, indices in file_match_indices:
            for idx in indices:
                flat_matches.append((fp, idx))

        total_matches = len(flat_matches)
        selected = flat_matches[offset:offset + limit] if offset else flat_matches[:limit]
        if not selected:
            return f"No matches for `{pattern_str}`"

        result_lines: list[str] = []
        for fp, idx in selected:
            rel = str(fp.relative_to(root))
            lines = lines_cache[str(fp)]
            display = lines[idx].rstrip("\n\r")
            if len(display) > MAX_LINE_LENGTH:
                display = display[:MAX_LINE_LENGTH] + "... (truncated)"
            result_lines.append(f"{rel}:{idx + 1}: {display}")
            for ci in range(max(0, idx - context), idx):
                ctx = lines[ci].rstrip("\n\r")
                if len(ctx) > MAX_LINE_LENGTH:
                    ctx = ctx[:MAX_LINE_LENGTH] + "... (truncated)"
                result_lines.append(f"{rel}:{ci + 1}- {ctx}")
            for ci in range(idx + 1, min(len(lines), idx + context + 1)):
                ctx = lines[ci].rstrip("\n\r")
                if len(ctx) > MAX_LINE_LENGTH:
                    ctx = ctx[:MAX_LINE_LENGTH] + "... (truncated)"
                result_lines.append(f"{rel}:{ci + 1}- {ctx}")

        result = "\n".join(result_lines)
        if len(selected) < total_matches:
            result += f"\n[Showing {len(selected)} of {total_matches} matches]"
        return result

    def _collect_matches(self, root: Path, pattern_str: str,
                          include: str | None) -> list[tuple[Path, list[int]]]:
        """Scan files and return (file_path, [match_line_index, ...]) pairs.
        Used by _py_search_files_only and _py_search_count.
        """
        try:
            pattern = re.compile(pattern_str)
        except re.error:
            return []

        include_glob = include or "*"
        matched_files = sorted(glob_module.glob(include_glob, root_dir=root, recursive=True))

        result: list[tuple[Path, list[int]]] = []
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
            indices = [i for i, line in enumerate(lines) if pattern.search(line)]
            if indices:
                result.append((fp, indices))

        result.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)
        return result
