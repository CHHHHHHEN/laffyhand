import glob as glob_module
from pathlib import Path
from typing import Any

from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.file._ripgrep import rg_available, glob as rg_glob


MAX_RESULTS = 100


class GlobTool(BaseTool):
    name = "glob"
    description = (
        "Find files matching a glob pattern. Results are sorted by modification time (newest first) "
        "and limited to 100 files. Uses ripgrep when available for faster results with .gitignore support."
    )
    max_result_size = 50000

    def _input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. **/*.py, src/**/*.ts)",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: current working directory)",
                },
            },
            "required": ["pattern"],
        }

    async def run(self, params: dict[str, Any]) -> str:
        root = Path(params.get("path", "."))
        pattern = params["pattern"]

        matches: list[Path] = []

        if rg_available():
            rg_results = rg_glob(root, pattern)
            if rg_results is not None:
                matches = [root / p for p in rg_results if p]

        if not matches:
            for p in glob_module.glob(pattern, root_dir=root, recursive=True):
                p_obj = root / p if root != Path(".") else Path(p)
                if p_obj.is_file():
                    matches.append(p_obj)

        if not matches:
            return f"No files found matching `{pattern}` in {root}"

        matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

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
        return result
