import glob as glob_module
from pathlib import Path
from typing import Any

from loguru import logger
from laffyhand.agent.tools.base import BaseTool


class GlobTool(BaseTool):
    name = "glob"
    description = "Find files matching a glob pattern."
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
        matches = sorted(glob_module.glob(pattern, root_dir=root, recursive=True))
        logger.info(f"Glob: pattern='{pattern}' in {root}, {len(matches)} matches")
        if not matches:
            return f"No files found matching `{pattern}` in {root}"
        return "\n".join(matches)
