"""Glob tool — list files matching a glob pattern.

Supports ripgrep (when available) for performance, with a
Python fallback. Results are sorted by mtime (newest first).
"""

import glob as glob_module
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field
from laffyhand.core.tools.base import BaseTool
from laffyhand.core.tools.file._gitignore import GitignoreFilter
from laffyhand.core.tools.file._ripgrep import rg_available, glob as rg_glob


_MAX_RESULTS = 100


def _is_within_root(target: Path, root: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class GlobParams(BaseModel):
    pattern: str = Field(
        description="Glob pattern to match (e.g. **/*.py, src/**/*.ts)"
    )
    path: str = Field(
        description="Directory to search. Absolute path recommended — use the workspace root from <env>."
    )
    exclude: str | None = Field(
        None,
        description="Glob pattern — matching files are skipped (e.g. __pycache__/**)",
    )
    include_ignored: bool = Field(
        False, description="If true, also include files that match .gitignore patterns"
    )


class GlobTool(BaseTool):
    name = "glob"
    path_params = ["path"]
    description = (
        "List files matching a glob pattern.\n\n"
        "**Required:** ``pattern`` + ``path``.\n\n"
        f"Results are sorted newest-first by mtime and capped at {_MAX_RESULTS}. "
        "Use **exclude** to skip files (e.g. ``__pycache__/**``). "
        ".gitignore is respected by default; **include_ignored** overrides it."
    )
    max_result_size = 50000

    def _input_schema(self) -> dict[str, Any]:
        return GlobParams.model_json_schema()

    async def run(self, params: dict[str, Any]) -> str:
        validated = GlobParams.model_validate(params)
        pattern = validated.pattern
        exclude = validated.exclude
        include_ignored = validated.include_ignored

        root = Path(validated.path).resolve()
        if not root.exists():
            return f"Path not found: {root}"
        if not root.is_dir():
            return f"Not a directory: {root}"

        matches: list[Path] = []

        if rg_available():
            rg_results = await rg_glob(
                root, pattern, include_ignored=include_ignored, exclude=exclude
            )
            if rg_results is not None:
                for p in rg_results:
                    if not p:
                        continue
                    p_obj = (root / p).resolve()
                    if not _is_within_root(p_obj, root):
                        logger.warning(f"Glob: blocked path traversal: {p_obj}")
                        continue
                    if p_obj.is_file():
                        matches.append(p_obj)
                logger.debug(
                    f"Glob: ripgrep returned {len(matches)} results for {pattern} in {root}"
                )

        if not matches:
            for p in glob_module.glob(pattern, root_dir=root, recursive=True):
                p_obj = (root / p).resolve()
                if not _is_within_root(p_obj, root):
                    logger.warning(f"Glob: blocked path traversal: {p_obj}")
                    continue
                if not p_obj.is_file():
                    continue
                if exclude and p_obj.match(exclude):
                    continue
                matches.append(p_obj)
            if not include_ignored and matches:
                gitignore = GitignoreFilter(root)
                matches = gitignore.filter(matches)
            logger.debug(
                f"Glob: Python glob returned {len(matches)} results for {pattern} in {root}"
            )

        if not matches:
            return f"No files found matching `{pattern}` in {root}"

        def _mtime(p: Path) -> float:
            try:
                return p.stat().st_mtime
            except OSError:
                return 0.0

        matches.sort(key=_mtime, reverse=True)

        truncated = len(matches) > _MAX_RESULTS
        if truncated:
            matches = matches[:_MAX_RESULTS]

        root_display = root.resolve()
        try:
            relative_matches = [str(p.relative_to(root_display)) for p in matches]
        except ValueError:
            relative_matches = [str(p) for p in matches]

        label = "file" if len(relative_matches) == 1 else "files"
        result = f"--- {len(relative_matches)} {label} ---\n"
        result += "\n".join(relative_matches)
        if truncated:
            result += f"\n[Results limited to {_MAX_RESULTS} files]"

        logger.info(f"Glob: {pattern} in {root} -> {len(matches)} file(s)")
        return result
