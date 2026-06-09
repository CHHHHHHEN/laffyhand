from __future__ import annotations

from pathlib import Path

from laffyhand.core.preference._walk import _walk_up


class PreferenceService:
    def __init__(self) -> None:
        self._preferences: str | None = None
        self._loaded_paths: set[str] = set()

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

    async def load_preferences(self, worktree: str) -> str:
        if self._preferences is not None:
            return self._preferences
        md = Path(worktree) / "AGENTS.md"
        if md.is_file():
            content = md.read_text(encoding="utf-8").strip()
            if content:
                self._preferences = f"<preference>\n{content}\n</preference>"
                self._loaded_paths.add(str(md))
                return self._preferences
        self._preferences = ""
        return ""

    def resolve_for_read(self, file_path: str, worktree: str) -> str | None:
        start = Path(file_path).resolve().parent
        stop = Path(worktree).resolve()
        sections: list[str] = []
        for md_path in self.find_up_all("AGENTS.md", start=start, stop=stop):
            sp = str(md_path)
            if sp in self._loaded_paths:
                continue
            self._loaded_paths.add(sp)
            content = md_path.read_text(encoding="utf-8").strip()
            if content:
                sections.append(f"Instructions from: {sp}\n{content}")
        if not sections:
            return None
        return "\n\n".join(sections)
