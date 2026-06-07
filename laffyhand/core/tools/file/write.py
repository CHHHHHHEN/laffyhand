"""Write tool — create or overwrite a file.

Supports atomic writes, line-ending preservation, and
interactive confirmation with diff preview.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from pydantic import BaseModel, Field
from laffyhand.core.tools.base import BaseTool
from laffyhand.core.tools.file._diff import format_diff
from laffyhand.core.tools.file._security import (
    atomic_write,
    blocked_write_path,
)
from laffyhand.core.tools.file._text_utils import (
    detect_line_ending,
    normalize_newlines,
)

if TYPE_CHECKING:
    from laffyhand.core.tools.permission import PermissionManager


class WriteParams(BaseModel):
    file_path: str = Field(
        description="The absolute path to the file to write (must be absolute, not relative)"
    )
    content: str = Field(description="Content to write to the file")
    confirm: bool | None = Field(
        None, description="If true, prompts for interactive confirmation before writing"
    )


class WriteTool(BaseTool):
    name = "write"
    path_params = ["file_path"]
    description = "Write content to a file, creating or overwriting it."
    max_result_size = 50000

    def __init__(self, permission_manager: PermissionManager | None = None) -> None:
        self._permission = permission_manager

    def _input_schema(self) -> dict[str, Any]:
        return WriteParams.model_json_schema()

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

        old_content: str | None = None
        if path.exists() and path.is_file():
            old_content = path.read_text(encoding="utf-8", errors="replace")
            line_ending = detect_line_ending(path)
            content = normalize_newlines(content, line_ending)

        # Interactive confirmation with diff preview
        confirm = params.get("confirm", False)
        if confirm:
            if self._permission is None:
                logger.warning(
                    "confirm=True but no permission manager available; skipping"
                )
            elif old_content is None:
                logger.info(
                    "confirm=True skipped for new file (no previous content to diff)"
                )
            else:
                allowed, reason = await self._permission.ask(
                    "write",
                    [str(path)],
                )
                if not allowed:
                    return reason or f"Write cancelled by user: {path}"

        try:
            await atomic_write(path, content)
        except OSError as e:
            logger.error(f"Write failed for {path}: {e}")
            return f"Write failed for {path}: internal error"

        # Post-write verification
        try:
            written = path.read_bytes()
            expected = content.encode("utf-8")
            if len(written) != len(expected):
                logger.warning(f"Write verification size mismatch for {path}")
        except Exception:
            logger.warning(f"Write verification read failed for {path}")

        result = f"File written: {path} ({len(content)} chars)"

        # Append diff for existing-file edits
        if old_content is not None:
            diff = format_diff(path, old_content, content)
            if diff.display.strip():
                result += f"\n\n{diff.display}"

        return result
