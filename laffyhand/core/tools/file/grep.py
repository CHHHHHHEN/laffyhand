"""Grep tool — search file contents with regex.

Uses ripgrep (when available) for performance, with a Python
fallback. Supports ``content``, ``files_only``, and ``count``
output modes, context lines, and pagination.
"""

import asyncio
import glob as glob_module
import re
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field
from laffyhand.core.tools.base import BaseTool
from laffyhand.core.tools.file._gitignore import GitignoreFilter
from laffyhand.core.tools.file._ripgrep import (
    rg_available,
    grep as rg_grep,
    grep_files as rg_grep_files,
    grep_count as rg_grep_count,
)

_MAX_RESULTS = 100
_MAX_LINE_LENGTH = 2000
_MAX_FILE_SIZE = 1_000_000


class GrepParams(BaseModel):
    """Search file contents with a regex pattern.

    Required: ``pattern`` + ``path``.
    """

    pattern: str = Field(description="Regex pattern to search for (required)")
    path: str = Field(description="Directory to search recursively, or a single file. Absolute path recommended — use the workspace root from <env>.")
    include: str | None = Field(None, description="Glob pattern — only files matching this are scanned (e.g. *.py for Python files)")
    exclude: str | None = Field(None, description="Glob pattern — matching files are skipped (e.g. test_*.py to exclude tests)")
    include_ignored: bool = Field(False, description="If true, also search files that match .gitignore patterns")
    output_mode: Literal["content", "files_only", "count"] = Field("content", description="content (default): matching lines with context; files_only: file paths only; count: per-file match counts")
    context: int = Field(0, description="Lines of context before and after each match (0 = matching line only)", ge=0)
    offset: int = Field(0, description="Number of initial results to skip (for pagination)", ge=0)
    limit: int = Field(_MAX_RESULTS, description=f"Maximum results to return (default {_MAX_RESULTS})", ge=1)


def _truncate_line(line: str) -> str:
    display = line.rstrip("\n\r")
    if len(display) > _MAX_LINE_LENGTH:
        display = display[:_MAX_LINE_LENGTH] + "... (truncated)"
    return display


class GrepTool(BaseTool):
    name = "grep"
    path_params = ["path"]
    description = (
        "Search file contents with a regex pattern.\n\n"
        "**Required:** ``pattern`` (regex), ``path`` (directory or file).\n\n"
        "**Output** depends on ``output_mode``:\n"
        "  - ``content`` (default) — ``file:line:content``, header ``--- N matches ---``\n"
        "  - ``files_only`` — file paths only\n"
        "  - ``count`` — ``file: N`` per-file counts\n\n"
        "Results are sorted newest-first by mtime and capped "
        f"at {_MAX_RESULTS}. Use ``offset``/``limit`` for pagination.\n\n"
        "**include**/**exclude** use glob syntax (e.g. ``*.py``).\n"
        "``.gitignore`` is respected by default; ``include_ignored`` overrides it."
    )
    max_result_size = 100_000

    def _input_schema(self) -> dict[str, Any]:
        return GrepParams.model_json_schema()

    async def run(self, params: dict[str, Any]) -> str:
        validated = GrepParams.model_validate(params)
        pattern_str = validated.pattern
        include = validated.include
        exclude = validated.exclude
        include_ignored = validated.include_ignored
        output_mode = validated.output_mode
        context = validated.context
        offset = validated.offset
        limit = validated.limit

        root = Path(validated.path).resolve()
        if not root.exists():
            return f"Path not found: {root}"

        if len(pattern_str) > 200:
            return f"Pattern too long ({len(pattern_str)} chars, max 200)"

        try:
            pattern = re.compile(pattern_str)
        except re.error as e:
            return f"Invalid regex pattern: {e}"

        if root.is_file():
            return await self._search_single_file(root, pattern, context, offset, limit)

        return await self._search_directory(
            root, pattern, include, exclude, include_ignored, output_mode, context, offset, limit,
        )

    # --- Helpers ---------------------------------------------------------------

    @staticmethod
    def _paginate(items: list[str], offset: int, limit: int, label: str = "matches") -> str:
        """Slice *items* with offset/limit, join with newlines, add summary."""
        selected = items[offset:offset + limit]
        if not selected:
            return ""
        result = "\n".join(selected)
        if len(selected) < len(items):
            result += f"\n[Showing {len(selected)} of {len(items)} {label}]"
        return result

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
            result.append(f"{file_label}:{ci + 1}- {_truncate_line(lines[ci])}")
        result.append(f"{file_label}:{idx + 1}: {_truncate_line(lines[idx])}")
        for ci in range(idx + 1, min(len(lines), idx + context + 1)):
            result.append(f"{file_label}:{ci + 1}- {_truncate_line(lines[ci])}")
        return result

    async def _search_single_file(
        self, path: Path, pattern: re.Pattern[str], context: int, offset: int, limit: int
    ) -> str:
        if not path.is_file():
            return f"Not a file: {path}"
        if path.stat().st_size > _MAX_FILE_SIZE:
            logger.info(f"Grep: skipped large file {path}")
            return f"Skipped (file too large): {path}"

        pattern_str = pattern.pattern

        # Try ripgrep first for performance
        if rg_available():
            raw = await rg_grep(path.parent, pattern_str, include=path.name, context=context, include_ignored=True)
            if raw is not None:
                lines = [ln.removeprefix("./") for ln in raw.splitlines() if ln.strip()]
                if not lines:
                    return f"No matches for `{pattern_str}` in {path}"
                lines = [_truncate_line(line) for line in lines]
                return self._paginate(lines, offset, limit, "lines")

        # Python fallback
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
        selected_indices = match_indices[offset:offset + limit]

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

        label = "match" if total_matches == 1 else "matches"
        result = f"--- {total_matches} {label} ---\n"
        result += "\n".join(result_lines)
        if len(selected_indices) < total_matches:
            result += f"\n[Showing {len(selected_indices)} of {total_matches} matches]"
        return result

    async def _search_directory(
        self,
        root: Path,
        pattern: re.Pattern[str],
        include: str | None,
        exclude: str | None,
        include_ignored: bool,
        output_mode: Literal["content", "files_only", "count"],
        context: int,
        offset: int,
        limit: int,
    ) -> str:
        pattern_str = pattern.pattern

        if rg_available():
            result = await self._rg_search(
                root, pattern_str, include, exclude, include_ignored,
                output_mode, context, offset, limit,
            )
            if result is not None:
                return result

        return await self._py_search(
            root, pattern, include, exclude, include_ignored,
            output_mode, context, offset, limit,
        )

    async def _rg_search(
        self,
        root: Path,
        pattern_str: str,
        include: str | None,
        exclude: str | None,
        include_ignored: bool,
        output_mode: Literal["content", "files_only", "count"],
        context: int,
        offset: int,
        limit: int,
    ) -> str | None:
        """Try ripgrep; return ``None`` to signal fallback to Python."""
        if output_mode == "files_only":
            raw_files = await rg_grep_files(root, pattern_str, include, include_ignored=include_ignored, exclude=exclude)
            if raw_files is None:
                return None
            files = [f.removeprefix("./") for f in raw_files]
            if not files:
                return f"No matches for `{pattern_str}`"
            return self._paginate(files, offset, limit, "files")

        if output_mode == "count":
            raw_str = await rg_grep_count(root, pattern_str, include, include_ignored=include_ignored, exclude=exclude)
        else:
            raw_str = await rg_grep(root, pattern_str, include, context, include_ignored=include_ignored, exclude=exclude)
        if raw_str is None:
            return None

        lines = [ln.removeprefix("./") for ln in raw_str.splitlines() if ln.strip()]
        if not lines:
            return f"No matches for `{pattern_str}`"

        if output_mode == "content":
            total = len(lines)
            lines = [_truncate_line(line) for line in lines]
            result = self._paginate(lines, offset, limit, "lines")
            if not result:
                return f"No matches for `{pattern_str}`"
            label = "line" if total == 1 else "lines"
            return f"--- {total} {label} ---\n{result}"

        return self._paginate(lines, offset, limit, "files")

    async def _py_search(
        self,
        root: Path,
        pattern: re.Pattern[str],
        include: str | None,
        exclude: str | None,
        include_ignored: bool,
        output_mode: Literal["content", "files_only", "count"],
        context: int,
        offset: int,
        limit: int,
    ) -> str:
        pattern_str = pattern.pattern
        logger.debug(f"Grep: Python fallback {output_mode} for `{pattern_str}` in {root}")
        stop_early = output_mode == "files_only"
        files_with_matches = await self._collect_matches(root, pattern, include, exclude, include_ignored, stop_early)

        if output_mode == "files_only":
            paths = [str(f.relative_to(root)) for f, _ in files_with_matches]
            return self._paginate(paths, offset, limit, "files") or f"No matches for `{pattern_str}`"

        if output_mode == "count":
            lines = [f"{f.relative_to(root)}: {len(m)}" for f, m in files_with_matches]
            return self._paginate(lines, offset, limit, "files") or f"No matches for `{pattern_str}`"

        # content mode
        flat_matches: list[tuple[Path, int]] = [
            (fp, idx) for fp, indices in files_with_matches for idx in indices
        ]
        if not flat_matches:
            return f"No matches for `{pattern_str}`"

        selected = flat_matches[offset:offset + limit]

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
                self._format_match_with_context(label, lines, idx, context, prev_idx)
            )
            prev_file = label
            prev_idx = idx

        total = len(flat_matches)
        label = "match" if total == 1 else "matches"
        result = f"--- {total} {label} ---\n"
        result += "\n".join(result_lines)
        if len(selected) < total:
            result += f"\n[Showing {len(selected)} of {total} matches]"
        return result

    async def _collect_matches(
        self, root: Path, pattern: re.Pattern[str], include: str | None,
        exclude: str | None = None, include_ignored: bool = False,
        stop_early: bool = False,
    ) -> list[tuple[Path, list[int]]]:
        """Scan files and return (file_path, [match_line_index, ...]) pairs.

        When *stop_early* is True, scanning a file stops at the first match
        (useful for ``files_only`` mode where counts are not needed).
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
                if fp.stat().st_size > _MAX_FILE_SIZE:
                    continue
                if exclude and fp.match(exclude):
                    continue
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                lines = text.splitlines(keepends=True)
                if stop_early:
                    if any(pattern.search(line) for line in lines):
                        result.append((fp, []))
                else:
                    indices = [i for i, line in enumerate(lines) if pattern.search(line)]
                    if indices:
                        result.append((fp, indices))

            # Apply .gitignore filtering (matching GlobTool / ListDirTool behavior)
            if not include_ignored:
                gitignore = GitignoreFilter(root)
                result = [
                    (fp, idx) for fp, idx in result if not gitignore.is_ignored(fp)
                ]

            result.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)
            return result

        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(loop.run_in_executor(None, _scan), timeout=30)
        except asyncio.TimeoutError:
            logger.warning(f"Grep: search timed out for pattern `{pattern.pattern}`")
            return []
