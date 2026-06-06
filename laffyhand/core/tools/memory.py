from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from laffyhand.core.tools.base import BaseTool

if TYPE_CHECKING:
    from laffyhand.core.memory.service import MemoryService


class MemoryParams(BaseModel):
    operation: str = Field(
        description="Operation: read, append, update, delete, clear"
    )
    entry: str | None = Field(
        None, description="Entry text (required for append, update)"
    )
    index: int | None = Field(
        None, description="Entry index (1-based, required for update, delete)"
    )


class MemoryTool(BaseTool):
    name = "memory"
    description = (
        "Manage persistent cross-session memory. "
        "Operations: read (view all entries), "
        "append (add a new entry), "
        "update (replace an entry by index), "
        "delete (remove an entry by index), "
        "clear (remove all entries)."
    )

    ParamsModel = MemoryParams

    def __init__(self, memory_service: MemoryService) -> None:
        super().__init__()
        self._memory = memory_service

    async def run(self, params: dict[str, Any]) -> str:
        op = params.get("operation", "")

        if op == "read":
            content = await self._memory.read()
            stripped = content.strip()
            if not stripped or stripped == "# Memory":
                return "Memory is empty."
            return content

        if op == "append":
            entry = params.get("entry")
            if not entry:
                return "Error: entry is required for append"
            ok, msg = await self._memory.append(entry)
            return msg

        if op == "update":
            index = params.get("index")
            entry = params.get("entry")
            if index is None:
                return "Error: index is required for update"
            if not entry:
                return "Error: entry is required for update"
            ok, msg = await self._memory.update(index, entry)
            return msg

        if op == "delete":
            index = params.get("index")
            if index is None:
                return "Error: index is required for delete"
            ok, msg = await self._memory.delete(index)
            return msg

        if op == "clear":
            ok, msg = await self._memory.clear()
            return msg

        return f"Error: unknown operation '{op}'. Use read, append, update, delete, or clear."
