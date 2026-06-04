from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathspec import PathSpec


_ZERO = object()


class GitignoreFilter:
    def __init__(self, search_root: Path) -> None:
        self._root = search_root.resolve()
        self._specs: list[tuple[Path, PathSpec]] = []
        for parent in [self._root] + list(self._root.parents):
            gitignore = parent / ".gitignore"
            if gitignore.is_file():
                from pathspec import PathSpec as _PS
                from pathspec.patterns import GitWildMatchPattern

                spec = _PS.from_lines(
                    GitWildMatchPattern,
                    gitignore.read_text(encoding="utf-8", errors="replace").splitlines(),
                )
                self._specs.append((parent, spec))

    def is_ignored(self, path: Path) -> bool:
        resolved = path.resolve()
        for gitignore_dir, spec in reversed(self._specs):
            try:
                rel = resolved.relative_to(gitignore_dir)
            except ValueError:
                continue
            if spec.match_file(str(rel)):
                return True
        return False

    def filter(
        self,
        paths: list[Path],
        include_ignored: bool = False,
    ) -> list[Path]:
        if include_ignored:
            return paths
        return [p for p in paths if not self.is_ignored(p)]
