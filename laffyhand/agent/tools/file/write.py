from pathlib import Path
from typing import Any

from laffyhand.agent.schemas import ToolResultContent
from laffyhand.agent.tools.base import BaseTool


class WriteTool(BaseTool):
    name = "write"
    description = "Write content to a file, creating or overwriting it."

    def _input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        }

    def run(self, params: dict[str, Any]) -> ToolResultContent:
        path = Path(params["file_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(params["content"], encoding="utf-8")
        return ToolResultContent(
            tool_call_id="",
            tool_name=self.name,
            result=f"File written: {path} ({len(params['content'])} chars)",
        )
