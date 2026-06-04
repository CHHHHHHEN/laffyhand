import difflib
import re
from pathlib import Path
from typing import Any

from loguru import logger
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.file._gitignore import GitignoreFilter
from laffyhand.agent.tools.file._security import looks_binary


MAX_CONSECUTIVE_READS = 4
MAX_CACHE_SIZE = 200


class ReadTool(BaseTool):
    name = "read"
    description = (
        "Read files or directories from the local filesystem. "
        "Supports line-numbered output, pattern-based context reading, and batch reading.\n\n"
        "To read a single file, provide file_path. "
        "Use offset (1-indexed) and limit for pagination (default limit: 2000). "
        "Any line longer than 2000 characters is truncated.\n\n"
        "To read around specific keywords, provide pattern (regex) and optional context (default 5). "
        "When pattern is given, offset/limit apply to matches, not raw lines.\n\n"
        "To read multiple files at once, provide paths (array of absolute paths).\n\n"
        "Directory listings show file line counts in parentheses. "
        "By default, files matching .gitignore patterns are excluded from directory listings; "
        "pass include_ignored=true to include them."
    )
    max_result_size = 50000

    def __init__(self, preference_resolver=None) -> None:
        self._read_cache: dict[str, tuple[float, str]] = {}
        self._consecutive: dict[str, int] = {}
        self._preference_resolver = preference_resolver

    def _input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Single absolute path to a file or directory to read",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Multiple absolute file paths to read at once",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start from (1-indexed) for normal reads; skip first N matches for pattern reads",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines or matches to return (defaults to 2000)",
                },
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to find lines of interest; shows matching lines with surrounding context (see context param)",
                },
                "context": {
                    "type": "integer",
                    "description": "Number of context lines before and after each match (default: 5). Only used with pattern",
                },
                "depth": {
                    "type": "integer",
                    "description": "Directory listing depth. 1 = flat, 2 = one level deep (default), etc. Only applies when file_path is a directory",
                },
                "include_ignored": {
                    "type": "boolean",
                    "description": "If true, include files that match .gitignore patterns in directory listings (default: false)",
                    "default": False,
                },
            },
            "anyOf": [
                {"required": ["file_path"]},
                {"required": ["paths"]},
            ],
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

    def _format_entry(
        self, entry: Path, indent: int, depth: int,
        gitignore: GitignoreFilter | None = None,
    ) -> list[str]:
        """Format a single directory entry. Recursively formats children when depth > 1."""
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
        self, path: Path, offset: int | None, limit: int | None, depth: int = 2,
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

    def _read_with_context(
        self,
        path: Path,
        pattern_str: str,
        context: int,
        offset: int | None,
        limit: int | None,
    ) -> str:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
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

        result = "".join(result_parts)
        if len(selected) < total_matches:
            result += f"\n[Showing {len(selected)} of {total_matches} matches]"

        return result

    async def run(self, params: dict[str, Any]) -> str:
        file_path: str | None = params.get("file_path")
        paths_input: Any = params.get("paths")

        if not file_path and not paths_input:
            return "Either file_path or paths is required"

        if file_path:
            return await self._run_single(file_path, params)

        if not isinstance(paths_input, list) or not paths_input:
            return "Either file_path or paths is required"

        paths: list[str] = [str(p) for p in paths_input]
        return await self._run_multi(paths, params)

    async def _run_single(self, file_path: str, params: dict[str, Any]) -> str:
        path = Path(file_path.strip())

        if not path.exists():
            msg = f"File not found: {path}"
            suggestions = self._suggest_similar(path)
            if suggestions:
                msg += "\nDid you mean?\n" + "\n".join(f"  {s}" for s in suggestions)
            return msg

        if path.is_dir():
            result = self._list_directory(
                path, params.get("offset"), params.get("limit"), params.get("depth", 2),
                params.get("include_ignored", False),
            )
            logger.info(f"Read: listed directory {path}")
            return result

        if looks_binary(path):
            logger.info(f"Read: skipped binary file {path}")
            return f"File appears to be binary and cannot be read as text: {path}"

        pattern = params.get("pattern")
        if pattern:
            context = params.get("context", 5)
            logger.info(
                f"Read: context read {path} pattern={pattern} context={context}"
            )
            return self._read_with_context(
                path, pattern, context, params.get("offset"), params.get("limit")
            )

        offset = params.get("offset")
        limit = params.get("limit")
        key = self._cache_key(path, offset, limit)

        try:
            current_mtime = path.stat().st_mtime
        except OSError:
            current_mtime = 0.0

        if key in self._read_cache:
            cached_mtime, cached_result = self._read_cache[key]
            if cached_mtime == current_mtime:
                self._consecutive[key] = self._consecutive.get(key, 0) + 1
                count = self._consecutive[key]
                if count >= MAX_CONSECUTIVE_READS:
                    return (
                        f"File `{path}` has been read {count} times consecutively "
                        "without changes. Try a different approach."
                    )
                return cached_result

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

        # ── Preference injection: walk upward from the read file ──
        if self._preference_resolver is not None:
            claim_id = params.get("_claim_id") or params.get("session_id") or ""
            instructions = self._preference_resolver(
                str(path.resolve()), claim_id
            )
            if instructions:
                pref_block = "\n".join(
                    f"<preference>\n{item['content']}\n</preference>"
                    for item in instructions
                )
                result = f"{pref_block}\n\n{result}"

        return result

    async def _run_multi(self, paths: list[str], params: dict[str, Any]) -> str:
        parts: list[str] = []
        total_size = 0
        max_size = self.max_result_size

        for p in paths:
            if total_size >= max_size:
                parts.append(f"... (result truncated, max {max_size} characters)")
                break

            path = Path(p)
            head = f"==== {p} ===="

            if not path.exists():
                parts.append(f"File not found: {p}")
                continue

            if path.is_dir():
                dir_content = self._list_directory(
                    path,
                    params.get("offset"),
                    params.get("limit"),
                    params.get("depth", 2),
                    params.get("include_ignored", False),
                )
                parts.append(f"{head}\n{dir_content}")
                total_size += len(dir_content) + len(head) + 2
                continue

            if looks_binary(path):
                parts.append(f"{head}\n(binary file)")
                total_size += len(head) + 15
                continue

            file_params: dict[str, Any] = {
                k: v for k, v in params.items() if k != "paths"
            }
            file_params["file_path"] = p
            result = await self._run_single(p, file_params)
            parts.append(f"{head}\n{result}")
            total_size += len(result)

        return "\n\n".join(parts)
