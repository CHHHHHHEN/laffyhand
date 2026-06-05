import asyncio
import glob as glob_module
import re
from pathlib import Path
from typing import Any

from loguru import logger
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.file._ripgrep import (
    rg_available,
    grep as rg_grep,
    grep_files as rg_grep_files,
    grep_count as rg_grep_count,
)

MAX_RESULTS = 100
MAX_LINE_LENGTH = 2000
MAX_FILE_SIZE = 1_000_000


class GrepTool(BaseTool):
    name = "grep"
    path_params = ["path"]
    description = (
        "Search file contents using a regular expression. "
        "Use absolute paths for the path parameter — prefix with the workspace directory from <env>. "
        "Results are sorted by file modification time (newest first) and limited to 100 matches. "
        "Uses ripgrep when available for significantly faster performance."
    )
    max_result_size = 100_000

    def _input_schema(self) -> dict[str, Any]:
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
                    "description": "Absolute directory or file to search in — must start with the workspace path from <env>",
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
            pattern = re.compile(pattern_str)
        except re.error as e:
            return f"Invalid regex pattern: {e}"

        if len(pattern_str) > 200:
            return f"Pattern too long ({len(pattern_str)} chars, max 200)"

        if root.is_file():
            return await self._search_single_file(
                root, pattern, context, offset, limit
            )

        return await self._search_directory(
            root, pattern, include, output_mode, context, offset, limit
        )

    @staticmethod
    def _truncate_line(line: str) -> str:
        display = line.rstrip("\n\r")
        if len(display) > MAX_LINE_LENGTH:
            display = display[:MAX_LINE_LENGTH] + "... (truncated)"
        return display

    def _format_match_with_context(
        self,
        file_label: str,
        lines: list[str],
        idx: int,
        context: int,
        prev_idx: int | None = None,
    ) -> list[str]:
        result: list[str] = []
        if context and prev_idx is not None and idx - prev_idx > 1:
            result.append("--")
        for ci in range(max(0, idx - context), idx):
            result.append(f"{file_label}:{ci + 1}- {self._truncate_line(lines[ci])}")
        result.append(f"{file_label}:{idx + 1}: {self._truncate_line(lines[idx])}")
        for ci in range(idx + 1, min(len(lines), idx + context + 1)):
            result.append(f"{file_label}:{ci + 1}- {self._truncate_line(lines[ci])}")
        return result

    async def _search_single_file(
        self, path: Path, pattern: re.Pattern[str], context: int, offset: int, limit: int
    ) -> str:
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

        loop = asyncio.get_running_loop()

        def _search_lines() -> tuple[list[str], list[int]]:
            lines_local = text.splitlines(keepends=True)
            indices = [i for i, line in enumerate(lines_local) if pattern.search(line)]
            return lines_local, indices

        try:
            lines, match_indices = await asyncio.wait_for(
                loop.run_in_executor(None, _search_lines), timeout=5
            )
        except asyncio.TimeoutError:
            return f"Search timed out for pattern `{pattern.pattern}` in {path}"

        if not match_indices:
            logger.info(f"Grep: no matches for `{pattern.pattern}` in {path}")
            return f"No matches for `{pattern.pattern}` in {path}"

        total_matches = len(match_indices)
        selected_indices = (
            match_indices[offset : offset + limit]
            if offset is not None
            else match_indices[:limit]
        )

        file_label = str(path)
        result_lines: list[str] = []
        prev_idx: int | None = None
        for idx in selected_indices:
            result_lines.extend(
                self._format_match_with_context(
                    file_label,
                    lines,
                    idx,
                    context,
                    prev_idx,
                )
            )
            prev_idx = idx

        result = "\n".join(result_lines)
        if len(selected_indices) < total_matches:
            result += f"\n[Showing {len(selected_indices)} of {total_matches} matches]"
        return result

    async def _search_directory(
        self,
        root: Path,
        pattern: re.Pattern[str],
        include: str | None,
        output_mode: str,
        context: int,
        offset: int,
        limit: int,
    ) -> str:
        pattern_str = pattern.pattern
        if output_mode == "files_only" and rg_available():
            result = await self._rg_files_only(root, pattern_str, include, offset, limit)
            if result is not None:
                return result

        if output_mode == "count" and rg_available():
            result = await self._rg_count(root, pattern_str, include, offset, limit)
            if result is not None:
                return result

        if output_mode == "content" and rg_available():
            result = await self._rg_content(
                root, pattern_str, include, context, offset, limit
            )
            if result is not None:
                return result

        if output_mode == "files_only":
            return await self._py_search_files_only(
                root, pattern, include, offset, limit
            )
        if output_mode == "count":
            return await self._py_search_count(
                root, pattern, include, offset, limit
            )
        return await self._py_search_content(
            root, pattern, include, context, offset, limit
        )

    async def _rg_files_only(
        self, root: Path, pattern_str: str, include: str | None, offset: int, limit: int
    ) -> str | None:
        results = await rg_grep_files(root, pattern_str, include)
        if results is None:
            return None

        total = len(results)
        selected = (
            results[offset : offset + limit] if offset is not None else results[:limit]
        )
        if not selected:
            return f"No matches for `{pattern_str}`"
        result = "\n".join(selected)
        if len(selected) < total:
            result += f"\n[Showing {len(selected)} of {total} files]"
        return result

    async def _rg_count(
        self, root: Path, pattern_str: str, include: str | None, offset: int, limit: int
    ) -> str | None:
        raw = await rg_grep_count(root, pattern_str, include)
        if raw is None:
            return None

        lines = [ln for ln in raw.splitlines() if ln.strip()]
        total = len(lines)
        selected = (
            lines[offset : offset + limit] if offset is not None else lines[:limit]
        )
        if not selected:
            return f"No matches for `{pattern_str}`"
        result = "\n".join(selected)
        if len(selected) < total:
            result += f"\n[Showing {len(selected)} of {total} files]"
        return result

    async def _rg_content(
        self,
        root: Path,
        pattern_str: str,
        include: str | None,
        context: int,
        offset: int,
        limit: int,
    ) -> str | None:
        raw = await rg_grep(root, pattern_str, include, context)
        if raw is None:
            return None

        lines = raw.splitlines()
        total = len(lines)
        selected = (
            lines[offset : offset + limit] if offset is not None else lines[:limit]
        )
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

    async def _py_search_files_only(
        self, root: Path, pattern: re.Pattern[str], include: str | None, offset: int, limit: int
    ) -> str:
        pattern_str = pattern.pattern
        logger.debug(f"Grep: Python fallback files_only for `{pattern_str}` in {root}")
        files_with_matches = await self._collect_matches(root, pattern, include)
        if not files_with_matches:
            return f"No matches for `{pattern_str}`"

        paths = [str(f.relative_to(root)) for f, _ in files_with_matches]
        total = len(paths)
        selected = (
            paths[offset : offset + limit] if offset is not None else paths[:limit]
        )
        if not selected:
            return f"No matches for `{pattern_str}`"
        result = "\n".join(selected)
        if len(selected) < total:
            result += f"\n[Showing {len(selected)} of {total} files]"
        return result

    async def _py_search_count(
        self, root: Path, pattern: re.Pattern[str], include: str | None, offset: int, limit: int
    ) -> str:
        pattern_str = pattern.pattern
        logger.debug(f"Grep: Python fallback count for `{pattern_str}` in {root}")
        files_with_matches = await self._collect_matches(root, pattern, include)
        if not files_with_matches:
            return f"No matches for `{pattern_str}`"

        result_lines = [
            f"{f.relative_to(root)}: {len(m)}" for f, m in files_with_matches
        ]
        total = len(result_lines)
        selected = (
            result_lines[offset : offset + limit]
            if offset is not None
            else result_lines[:limit]
        )
        if not selected:
            return f"No matches for `{pattern_str}`"
        result = "\n".join(selected)
        if len(selected) < total:
            result += f"\n[Showing {len(selected)} of {total} files]"
        return result

    async def _py_search_content(
        self,
        root: Path,
        pattern: re.Pattern[str],
        include: str | None,
        context: int,
        offset: int,
        limit: int,
    ) -> str:
        pattern_str = pattern.pattern
        logger.debug(f"Grep: Python fallback content for `{pattern_str}` in {root}")
        files_with_matches = await self._collect_matches(root, pattern, include)
        if not files_with_matches:
            return f"No matches for `{pattern_str}`"

        flat_matches: list[tuple[Path, int]] = []
        for fp, indices in files_with_matches:
            for idx in indices:
                flat_matches.append((fp, idx))

        total_matches = len(flat_matches)
        selected = (
            flat_matches[offset : offset + limit]
            if offset is not None
            else flat_matches[:limit]
        )
        if not selected:
            return f"No matches for `{pattern_str}`"

        lines_cache: dict[str, list[str]] = {}
        result_lines: list[str] = []
        prev_file: str | None = None
        prev_idx: int | None = None
        for fp, idx in selected:
            label = str(fp.relative_to(root))
            if label not in lines_cache:
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                lines_cache[label] = text.splitlines(keepends=True)
            lines = lines_cache[label]
            if prev_file is not None and prev_file != label:
                prev_idx = None
            result_lines.extend(
                self._format_match_with_context(
                    label,
                    lines,
                    idx,
                    context,
                    prev_idx,
                )
            )
            prev_file = label
            prev_idx = idx

        result = "\n".join(result_lines)
        if len(selected) < total_matches:
            result += f"\n[Showing {len(selected)} of {total_matches} matches]"
        return result

    async def _collect_matches(
        self, root: Path, pattern: re.Pattern[str], include: str | None
    ) -> list[tuple[Path, list[int]]]:
        """Scan files and return (file_path, [match_line_index, ...]) pairs.
        Used by _py_search_files_only and _py_search_count.
        """

        include_glob = include or "*"

        def _scan() -> list[tuple[Path, list[int]]]:
            glob_pattern = "**/" + include_glob
            matched_files = sorted(
                glob_module.glob(glob_pattern, root_dir=root, recursive=True)
            )
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

        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(loop.run_in_executor(None, _scan), timeout=30)
        except asyncio.TimeoutError:
            logger.warning(f"Grep: search timed out for pattern `{pattern.pattern}`")
            return []
