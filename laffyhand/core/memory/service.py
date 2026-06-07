from __future__ import annotations

import asyncio
from pathlib import Path

_MEMORY_SYSTEM_PROMPT = """\
<memory-rules>
You have memory tools available to preserve information across sessions.
At the **end of each task**, evaluate whether any information from this session
is worth retaining for future work. If so, use the memory tools to record it.
Record faithfully — do not fabricate, distort, or infer beyond what was actually observed or stated.

### What to Remember

Prefer information that is **stable, general, and reusable**:

- facts or patterns likely to benefit future sessions
- cross-cutting context that would be costly to rediscover
- future mistakes that might be repeated

### What NOT to Remember

Skip information that is **transient, context-bound, or already evident**:

- content that only makes sense within the current Session
- your own reasoning steps or intermediate output
- anything already captured (check before writing)

### When Capacity Is Limited

The memory store has a configured length limit. When approaching it:

1. **Consolidate** — merge new info into existing entries instead of appending
2. **Replace** — if an entry is superseded, update it rather than adding alongside
3. **Drop** — if nothing passes the bar above, leave memory unchanged
</memory-rules>"""


class MemoryFormatError(ValueError):
    """Raised when Memory.md content is not in the expected numbered-list format."""


class MemoryService:
    def __init__(self, path: str, max_length: int) -> None:
        self._path = Path(path)
        self._max_length = max_length
        self._lock = asyncio.Lock()

    @property
    def system_prompt(self) -> str:
        return _MEMORY_SYSTEM_PROMPT

    async def read(self) -> str:
        if not self._path.exists():
            return "# Memory\n"
        return self._path.read_text(encoding="utf-8")

    def _parse_entries(self, content: str) -> list[str]:
        entries: list[str] = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            if line == "# Memory":
                continue
            idx = line.find(". ")
            if idx > 0 and line[:idx].strip().isdigit():
                entries.append(line[idx + 2:].strip())
            else:
                raise MemoryFormatError(
                    f"Unexpected line (not a numbered entry): {line!r}"
                )
        return entries

    def _format_entries(self, entries: list[str]) -> str:
        lines = ["# Memory"]
        for i, entry in enumerate(entries, 1):
            lines.append(f"{i}. {entry}")
        lines.append("")
        return "\n".join(lines)

    def _check_length(self, content: str) -> bool:
        return len(content) <= self._max_length

    async def append(self, entry: str) -> tuple[bool, str]:
        async with self._lock:
            content = await self._read_locked()
            stripped = content.strip()
            if not stripped or stripped == "# Memory":
                entries: list[str] = []
            else:
                try:
                    entries = self._parse_entries(content)
                except MemoryFormatError as e:
                    return False, str(e)
            entries.append(entry)
            new_content = self._format_entries(entries)
            if not self._check_length(new_content):
                return False, (
                    f"Error: memory would exceed max length of {self._max_length} chars. "
                    f"Try consolidating existing entries before adding more."
                )
            self._path.write_text(new_content, encoding="utf-8")
            return True, f"Appended entry {len(entries)}"

    async def update(self, index: int, entry: str) -> tuple[bool, str]:
        async with self._lock:
            content = await self._read_locked()
            try:
                entries = self._parse_entries(content)
            except MemoryFormatError as e:
                return False, str(e)
            if index < 1 or index > len(entries):
                return False, (
                    f"Error: entry index {index} out of range (1-{len(entries)}). "
                    f"Use 'read' to see current entries."
                )
            entries[index - 1] = entry
            new_content = self._format_entries(entries)
            if not self._check_length(new_content):
                return False, (
                    f"Error: memory would exceed max length of {self._max_length} chars. "
                    f"Try consolidating existing entries before adding more."
                )
            self._path.write_text(new_content, encoding="utf-8")
            return True, f"Updated entry {index}"

    async def delete(self, index: int) -> tuple[bool, str]:
        async with self._lock:
            content = await self._read_locked()
            try:
                entries = self._parse_entries(content)
            except MemoryFormatError as e:
                return False, str(e)
            if index < 1 or index > len(entries):
                return False, (
                    f"Error: entry index {index} out of range (1-{len(entries)}). "
                    f"Use 'read' to see current entries."
                )
            removed = entries.pop(index - 1)
            new_content = self._format_entries(entries)
            self._path.write_text(new_content, encoding="utf-8")
            return True, f"Deleted entry {index}: {removed}"

    async def clear(self) -> tuple[bool, str]:
        async with self._lock:
            self._path.write_text("# Memory\n", encoding="utf-8")
        return True, "Memory cleared"

    async def _read_locked(self) -> str:
        """Read file content (caller must hold self._lock)."""
        if not self._path.exists():
            return "# Memory\n"
        return self._path.read_text(encoding="utf-8")


__all__ = ["MemoryService", "MemoryFormatError", "_MEMORY_SYSTEM_PROMPT"]
