"""Read tool — view file contents with line numbers and pattern search.

Supports pagination (offset/limit), pattern-based context reading,
and automatic binary-file detection.
"""

import asyncio
import difflib
import re
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field
from laffyhand.core.tools.base import BaseTool
from laffyhand.core.tools.file._security import looks_binary


class ReadParams(BaseModel):
    file_path: str = Field(description="Absolute path to a file to read")
    offset: int | None = Field(None, description="Line number to start from (1-indexed) for normal reads; skip first N matches for pattern reads")
    limit: int | None = Field(2000, description="Maximum number of lines or matches to return (default: 2000)")
    pattern: str | None = Field(None, description="Regex pattern to find lines of interest; shows matching lines with surrounding context (see context param)")
    context: int | None = Field(None, description="Number of context lines before and after each match (default: 5). Only used with pattern")


class ReadTool(BaseTool):
    name = "read"
    path_params = ["file_path"]
    description = (
        "Read a text file with line-numbered output.\n\n"
        "**Required:** ``file_path``.\n\n"
        "Use ``offset`` (1-indexed) and ``limit`` for pagination "
        "(default limit: 2000). Lines longer than 2000 chars are truncated.\n\n"
        "To find specific content, pass ``pattern`` (regex) and optional "
        "``context`` (default 5). Matches are prefixed with ``>``.\n\n"
        "Use the list_dir tool for directory listings."
    )
    max_result_size = 50000

    def _input_schema(self) -> dict[str, Any]:
        return ReadParams.model_json_schema()

    def _suggest_similar(self, path: Path) -> list[str]:
        if not path.parent.exists():
            return []
        try:
            candidates = [p.name for p in path.parent.iterdir() if p.is_file()]
        except PermissionError:
            return []
        return difflib.get_close_matches(path.name, candidates, n=5, cutoff=0.3)

    async def _read_with_context(
        self,
        path: Path,
        pattern_str: str,
        context: int,
        offset: int | None,
        limit: int | None,
    ) -> str:
        try:
            text = await asyncio.to_thread(
                path.read_text, encoding="utf-8", errors="replace"
            )
        except Exception as e:
            return f"Error reading {path}: {e}"

        lines = text.splitlines(keepends=True)
        total_lines = len(lines)

        try:
            pattern = re.compile(pattern_str)
        except re.error as e:
            return f"Invalid regex pattern: {e}"

        match_indices = [i for i, line in enumerate(lines) if pattern.search(line)]
        if not match_indices:
            return f"No matches for `{pattern_str}` in {path}"

        total_matches = len(match_indices)
        start = offset if offset is not None else 0
        end = total_matches if limit is None else start + limit
        selected = match_indices[start:end]

        line_num_width = max(4, len(str(total_lines)))
        result_parts: list[str] = []

        # Build context ranges and merge overlapping ones
        groups: list[tuple[int, int, list[int]]] = []
        for idx in selected:
            start = max(0, idx - context)
            end = min(total_lines, idx + context + 1)
            if groups and start <= groups[-1][1]:
                prev_start, prev_end, prev_matches = groups[-1]
                groups[-1] = (prev_start, max(prev_end, end), prev_matches + [idx])
            else:
                groups.append((start, end, [idx]))

        for gi, (start, end, group_matches) in enumerate(groups):
            if gi > 0:
                result_parts.append("--\n")

            for ci in range(start, end):
                line = lines[ci]
                line_num = f"{ci + 1:>{line_num_width}d}"
                marker = ">" if ci in group_matches else " "
                if len(line) > 2000:
                    line = line[:2000]
                    if line.endswith("\n"):
                        line = line[:-1]
                    line += "... (line truncated to 2000 chars)\n"
                if not line.endswith("\n"):
                    line += "\n"
                result_parts.append(f"{line_num}{marker}{line}")

        header = f"--- {total_matches} match{'es' if total_matches != 1 else ''} in {path} ---\n"
        result = header + "".join(result_parts)
        if len(selected) < total_matches:
            result += f"\n[Showing {len(selected)} of {total_matches} matches]"

        return result

    async def run(self, params: dict[str, Any]) -> str:
        file_path: str | None = params.get("file_path")

        if not file_path:
            return "file_path is required"

        path = Path(file_path.strip())

        exists = await asyncio.to_thread(path.exists)
        if not exists:
            msg = f"File not found: {path}"
            suggestions = await asyncio.to_thread(self._suggest_similar, path)
            if suggestions:
                msg += "\nDid you mean?\n" + "\n".join(f"  {s}" for s in suggestions)
            return msg

        is_dir = await asyncio.to_thread(path.is_dir)
        if is_dir:
            return f"'{path}' is a directory. Use the list_dir tool to list directory contents."

        is_bin = await asyncio.to_thread(looks_binary, path)
        if is_bin:
            logger.info(f"Read: skipped binary file {path}")
            return f"File appears to be binary and cannot be read as text: {path}"

        pattern = params.get("pattern")
        if pattern:
            context = params.get("context", 5)
            logger.info(
                f"Read: context read {path} pattern={pattern} context={context}"
            )
            return await self._read_with_context(
                path, pattern, context, params.get("offset"), params.get("limit")
            )

        offset = params.get("offset")
        limit = params.get("limit")

        text = await asyncio.to_thread(
            path.read_text, encoding="utf-8", errors="replace"
        )
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

        header = f"--- {path} ({total_lines} lines, showing {len(selected)}) ---\n"
        result = header + "".join(result_parts)

        if offset is None and limit is None and len(text) > self.max_result_size:
            result += f"\n[File is large ({len(text)} bytes). Use offset and limit to read specific sections.]"

        logger.info(
            f"Read: {path} ({total_lines} lines, offset={offset}, limit={limit})"
        )

        return result
