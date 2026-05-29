import re
from pathlib import Path
from typing import Any

from laffyhand.agent.schemas import ToolResultContent
from laffyhand.agent.tools.base import BaseTool


class GrepTool(BaseTool):
    name = "grep"
    description = "Search file contents using a regular expression."

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

    def run(self, params: dict[str, Any]) -> ToolResultContent:
        root = Path(params.get("path", "."))
        pattern = re.compile(params["pattern"])
        include = params.get("include", "*")

        matches: list[str] = []
        for fp in sorted(root.rglob(include)):
            if not fp.is_file():
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(text.splitlines(), 1):
                    if pattern.search(line):
                        matches.append(f"{fp}:{i}: {line}")
            except Exception as e:
                matches.append(f"{fp}: error: {e}")

        if not matches:
            return ToolResultContent(
                tool_call_id="", tool_name=self.name,
                result=f"No matches for `{params['pattern']}`",
            )
        return ToolResultContent(
            tool_call_id="", tool_name=self.name,
            result="\n".join(matches),
        )
