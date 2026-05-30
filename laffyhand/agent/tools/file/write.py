import os
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.file._security import blocked_write_path


def _detect_line_ending(path: Path, sample_size: int = 4096) -> str:
    """Detect whether a file uses \\r\\n or \\n line endings."""
    try:
        with path.open("rb") as f:
            sample = f.read(sample_size)
        crlf = sample.count(b"\r\n")
        lf = sample.count(b"\n") - crlf
        return "\r\n" if crlf > lf else "\n"
    except Exception:
        return "\n"


def _normalize_newlines(text: str, line_ending: str) -> str:
    """Normalize internal newlines to the target line ending."""
    if line_ending == "\n":
        return text.replace("\r\n", "\n")
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


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

        # Check sensitive paths
        block_reason = blocked_write_path(path)
        if block_reason:
            return f"Blocked: {block_reason}: {path}"

        content = params.get("content")
        if content is None:
            content = ""

        # Normalize line endings to match existing file convention
        if path.exists() and path.is_file():
            line_ending = _detect_line_ending(path)
            content = _normalize_newlines(content, line_ending)

        path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            Path(tmp).replace(path)
        except OSError as e:
            Path(tmp).unlink(missing_ok=True)
            logger.error(f"Write failed for {path}: {e}")
            return f"Write failed for {path}: {e}"
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            logger.error(f"Write failed for {path}")
            raise

        # Post-write verification: re-read and compare bytes
        try:
            written = path.read_bytes()
            expected = content.encode("utf-8")
            if len(written) != len(expected):
                logger.warning(f"Write verification mismatch for {path}")
        except Exception:
            logger.warning(f"Write verification read failed for {path}")

        return f"File written: {path} ({len(content)} chars)"
