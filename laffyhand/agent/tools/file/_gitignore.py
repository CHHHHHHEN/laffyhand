from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathspec import PathSpec


_ZERO = object()


# Module-level cache: root_resolved -> (mtime_sum, specs)
_GITIGNORE_CACHE: dict[Path, tuple[float, list[tuple[Path, "PathSpec"]]]] = {}
_GITIGNORE_CACHE_MAX = 64
_GITIGNORE_CACHE_TTL = 5.0


def _load_gitignore_specs(search_root: Path) -> list[tuple[Path, "PathSpec"]]:
    """Load .gitignore specs for *search_root* with module-level caching."""
    root_resolved = search_root.resolve()
    now = time.monotonic()

    cached = _GITIGNORE_CACHE.get(root_resolved)
    if cached is not None:
        _ts, cached_specs = cached
        if now - _ts < _GITIGNORE_CACHE_TTL:
            return cached_specs

    from pathspec import PathSpec as _PS
    from pathspec.patterns import GitWildMatchPattern

    specs: list[tuple[Path, "PathSpec"]] = []
    for parent in [root_resolved] + list(root_resolved.parents):
        gitignore = parent / ".gitignore"
        if gitignore.is_file():
            spec = _PS.from_lines(
                GitWildMatchPattern,
                gitignore.read_text(encoding="utf-8", errors="replace").splitlines(),
            )
            specs.append((parent, spec))

    _GITIGNORE_CACHE[root_resolved] = (now, specs)
    if len(_GITIGNORE_CACHE) > _GITIGNORE_CACHE_MAX:
        oldest = next(iter(_GITIGNORE_CACHE))
        del _GITIGNORE_CACHE[oldest]

    return specs


class GitignoreFilter:
    def __init__(self, search_root: Path) -> None:
        self._root = search_root.resolve()
        self._specs = _load_gitignore_specs(self._root)

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
