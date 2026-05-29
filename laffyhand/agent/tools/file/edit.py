from pathlib import Path
from typing import Any

from laffyhand.agent.tools.base import BaseTool


class EditTool(BaseTool):
    name = "edit"
    description = "Perform an exact string replacement in a file."

    def _input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The text to replace it with",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    def run(self, params: dict[str, Any]) -> str:
        path = Path(params["file_path"])
        if not path.exists():
            return f"File not found: {path}"

        old = params["old_string"]
        new = params["new_string"]
        content = path.read_text(encoding="utf-8")

        if old not in content:
            return f"old_string not found in {path}"

        count = content.count(old)
        if count > 1:
            return f"Found {count} matches for old_string in {path}. Provide more surrounding context."

        new_content = content.replace(old, new, 1)
        path.write_text(new_content, encoding="utf-8")
        return f"Edited {path}: replaced 1 occurrence"
