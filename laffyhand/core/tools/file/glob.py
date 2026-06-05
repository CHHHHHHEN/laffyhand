import glob as glob_module
from pathlib import Path
from typing import Any

from loguru import logger
from laffyhand.core.tools.base import BaseTool
from laffyhand.core.tools.file._gitignore import GitignoreFilter
from laffyhand.core.tools.file._ripgrep import rg_available, glob as rg_glob


MAX_RESULTS = 100


def _is_within_root(target: Path, root: Path) -> bool:
    """Check whether *target* resolves to a path inside *root*."""
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class GlobTool(BaseTool):
    name = "glob"
    path_params = ["path"]
    description = (
        "Find files matching a glob pattern. Results are sorted by modification time (newest first) "
        "and limited to 100 files. By default, files matched by .gitignore patterns are excluded. "
        "Uses ripgrep when available for faster results with native .gitignore support.\n\n"
        "Parameters:\n"
        "- pattern: glob pattern (e.g. **/*.py, src/**/*.ts)\n"
        "- path: absolute search directory — must start with the workspace path from <env>\n"
        "- include_ignored: if true, include files that match .gitignore patterns (default: false)"
    )
    max_result_size = 50000

    def _input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. **/*.py, src/**/*.ts)",
                },
                "path": {
                    "type": "string",
                    "description": "Absolute search directory — must start with the workspace path from <env>",
                },
                "include_ignored": {
                    "type": "boolean",
                    "description": "If true, include files that match .gitignore patterns (default: false)",
                    "default": False,
                },
            },
            "required": ["pattern"],
        }

    async def run(self, params: dict[str, Any]) -> str:
        root = Path(params.get("path", ".")).resolve()
        pattern = params["pattern"]
        include_ignored = params.get("include_ignored", False)

        matches: list[Path] = []

        if rg_available():
            rg_results = await rg_glob(root, pattern, include_ignored=include_ignored)
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
                if p_obj.is_file():
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

        truncated = len(matches) > MAX_RESULTS
        if truncated:
            matches = matches[:MAX_RESULTS]

        root_display = root.resolve()
        try:
            relative_matches = [str(p.relative_to(root_display)) for p in matches]
        except ValueError:
            relative_matches = [str(p) for p in matches]

        result = "\n".join(relative_matches)
        if truncated:
            result += f"\n[Results limited to {MAX_RESULTS} files]"

        logger.info(f"Glob: {pattern} in {root} -> {len(matches)} file(s)")
        return result
