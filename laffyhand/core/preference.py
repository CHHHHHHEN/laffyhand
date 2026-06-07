from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path

from loguru import logger


def _walk_up(
    target: str,
    start: Path | None = None,
    stop: Path | None = None,
) -> Iterator[Path]:
    if start is None:
        start = Path(os.getcwd()).resolve()
    if stop is None:
        stop = Path(os.path.expanduser("~")).resolve()
    current = start.resolve()
    while True:
        yield current / target
        if current == stop or current.parent == current:
            break
        current = current.parent


class PreferenceService:
    """Manages AGENTS.md preference files: discovery, caching, polling, and per-message claims."""

    def __init__(self) -> None:
        self._preferences: str | None = None
        self._preference_files: dict[str, str] = {}
        self._pref_lock = asyncio.Lock()
        self._prefs_initialized: bool = False
        self._pref_claims: dict[str, set[str]] = {}

    # ── file walking utilities ──────────────────────────────────

    @staticmethod
    def find_up(
        target: str,
        start: Path | None = None,
        stop: Path | None = None,
    ) -> Path | None:
        for candidate in _walk_up(target, start, stop):
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def find_up_all(
        target: str,
        start: Path | None = None,
        stop: Path | None = None,
    ) -> list[Path]:
        return [c for c in _walk_up(target, start, stop) if c.is_file()]

    # ── preference loading / caching ────────────────────────────

    def _read_preference_files(self) -> dict[str, str]:
        result: dict[str, str] = {}
        project_md = self.find_up("AGENTS.md")
        if project_md is not None:
            result[str(project_md)] = project_md.read_text(encoding="utf-8").strip()
            return result
        home_md = Path(os.path.expanduser("~")) / "AGENTS.md"
        if home_md.is_file():
            result[str(home_md)] = home_md.read_text(encoding="utf-8").strip()
        return result

    async def load_preferences(self, workspace: str | None = None) -> str:
        async with self._pref_lock:
            if self._preferences is not None:
                return self._preferences
            self._preference_files = self._read_preference_files()
            sections = [
                f"<preference>\n{text}\n</preference>"
                for text in self._preference_files.values()
            ]
            self._preferences = "\n".join(sections) if sections else ""
            self._prefs_initialized = True
            return self._preferences

    async def poll_new_preferences(self) -> str:
        current = self._read_preference_files()
        async with self._pref_lock:
            if not self._prefs_initialized:
                self._preference_files = current
                return ""
            changed = False
            sections: list[str] = []
            for path, text in current.items():
                prev = self._preference_files.get(path)
                if prev == text:
                    continue
                self._preference_files[path] = text
                sections.append(f"<preference>\n{text}\n</preference>")
                changed = True
                logger.info(f"New/changed preferences: {path}")
            for path in list(self._preference_files):
                if path not in current:
                    del self._preference_files[path]
                    changed = True
                    logger.info(f"Removed preferences from deleted file: {path}")
            if changed:
                self._preferences = None
        return "\n".join(sections) if sections else ""

    # ── per-message preference resolution ───────────────────────

    def resolve_preferences(
        self,
        file_path: str,
        message_id: str,
        *,
        root: str | None = None,
    ) -> list[dict[str, str]]:
        start = Path(file_path).resolve().parent
        stop = Path(root).resolve() if root else Path(os.getcwd()).resolve()
        results: list[dict[str, str]] = []
        found = self.find_up_all("AGENTS.md", start=start, stop=stop)
        claims = self._pref_claims.setdefault(message_id, set())
        for md_path in found:
            sp = str(md_path)
            if sp in claims:
                continue
            claims.add(sp)
            content = md_path.read_text(encoding="utf-8").strip()
            if content:
                results.append(
                    {
                        "filepath": sp,
                        "content": f"Instructions from: {sp}\n{content}",
                    }
                )
        return results

    def clear_preference_claims(self, message_id: str) -> None:
        self._pref_claims.pop(message_id, None)


__all__ = ["PreferenceService"]
