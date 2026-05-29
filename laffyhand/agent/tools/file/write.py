import tempfile
from pathlib import Path
from typing import Any

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

    def run(self, params: dict[str, Any]) -> str:
        path = Path(params["file_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        content = params["content"]
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(content)
            Path(tmp).replace(path)
        except:
            Path(tmp).unlink(missing_ok=True)
            raise
        return f"File written: {path} ({len(content)} chars)"
