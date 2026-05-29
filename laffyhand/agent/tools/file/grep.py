import glob as glob_module
import re
from pathlib import Path
from typing import Any

from loguru import logger
from laffyhand.agent.tools.base import BaseTool


class GrepTool(BaseTool):
    name = "grep"
    description = "Search file contents using a regular expression."
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
                    "description": "Directory to search in (default: current working directory)",
                },
            },
            "required": ["pattern"],
        }

    def run(self, params: dict[str, Any]) -> str:
        root = Path(params.get("path", "."))
        try:
            pattern = re.compile(params["pattern"])
        except re.error as e:
            return f"Invalid regex pattern: {e}"
        include = params.get("include", "*")
        max_size = 1_000_000

        matched_files = sorted(glob_module.glob(include, root_dir=root, recursive=True))
        logger.info(f"Grep: pattern='{params['pattern']}' in {root}, {len(matched_files)} files to search")
        matches: list[str] = []
        for rel_path in matched_files:
            fp = root / rel_path
            if not fp.is_file():
                continue
            if fp.stat().st_size > max_size:
                matches.append(f"{fp}: skipped (file too large)")
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(text.splitlines(), 1):
                    if pattern.search(line):
                        matches.append(f"{fp}:{i}: {line}")
            except Exception as e:
                matches.append(f"{fp}: error: {e}")

        if not matches:
            return f"No matches for `{params['pattern']}`"
        return "\n".join(matches)
