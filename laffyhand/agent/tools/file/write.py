from pathlib import Path
from typing import Any

from loguru import logger
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.file._security import (
    atomic_write,
    blocked_write_path,
    detect_line_ending,
    normalize_newlines,
)


class WriteTool(BaseTool):
    name = "write"
    description = "Write content to a file, creating or overwriting it."

    def _input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file to write (must be absolute, not relative)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        }

    async def run(self, params: dict[str, Any]) -> str:
        raw = params["file_path"]
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()

        block_reason = blocked_write_path(path)
        if block_reason:
            return f"Blocked: {block_reason}: {path}"

        content = params.get("content")
        if content is None:
            content = ""

        if path.exists() and path.is_file():
            line_ending = detect_line_ending(path)
            content = normalize_newlines(content, line_ending)

        try:
            atomic_write(path, content)
        except OSError as e:
            logger.error(f"Write failed for {path}: {e}")
            return f"Write failed for {path}: {e}"

        try:
            written = path.read_bytes()
            expected = content.encode("utf-8")
            if len(written) != len(expected):
                logger.warning(f"Write verification size mismatch for {path}")
        except Exception:
            logger.warning(f"Write verification read failed for {path}")

        return f"File written: {path} ({len(content)} chars)"
