from pathlib import Path
from typing import Any

from laffyhand.agent.schemas import ToolResultContent
from laffyhand.agent.tools.base import BaseTool


class ReadTool(BaseTool):
    name = "read"
    description = "Read the contents of a file. Use offset and limit to read specific line ranges."
    max_result_size = 50000

    def _input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start from (1-indexed)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read",
                },
            },
            "required": ["file_path"],
        }

    def run(self, params: dict[str, Any]) -> ToolResultContent:
        path = Path(params["file_path"])
        if not path.exists():
            return ToolResultContent(tool_call_id="", tool_name=self.name, result=f"File not found: {path}")
        if not path.is_file():
            return ToolResultContent(tool_call_id="", tool_name=self.name, result=f"Not a file: {path}")

        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines(keepends=True)

        offset = params.get("offset")
        limit = params.get("limit")

        if offset is not None:
            if offset < 1:
                return ToolResultContent(
                    tool_call_id="", tool_name=self.name,
                    result=f"Invalid offset: {offset}. Offset must be >= 1.",
                )
            lines = lines[offset - 1:]
        if limit is not None:
            lines = lines[:limit]

        result = "".join(lines)

        return ToolResultContent(tool_call_id="", tool_name=self.name, result=result)
