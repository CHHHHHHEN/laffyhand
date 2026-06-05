""".gitignore rule parsing and path filtering.

Provides GitignoreFilter to check whether paths are ignored by
.gitignore rules.  A module-level OrderedDict cache with dual
invalidation (TTL + mtime) avoids re-parsing the same directory
tree on every lookup.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathspec import PathSpec

# --- Cache internals ----------------------------------------------------------

_SpecEntry = list[tuple[Path, "PathSpec", float]]
_CacheValue = tuple[float, _SpecEntry]

# OrderedDict enables FIFO eviction + MRU promotion on cache hit.
_GITIGNORE_CACHE: OrderedDict[Path, _CacheValue] = OrderedDict()
_GITIGNORE_CACHE_MAX = 64
_GITIGNORE_CACHE_TTL = 5.0


def _load_gitignore_specs(search_root: Path) -> _SpecEntry:
    """Load .gitignore specs for *search_root*, walking up to filesystem root.

    Returns a list of (gitignore_dir, PathSpec, mtime) ordered from closest
    ancestor to farthest (leaf → /).  Each entry holds the *PathSpec* parsed
    from one ``.gitignore`` file along with its parent directory (for path
    scoping) and the file's mtime (for cache validation).
    """
    root_resolved = search_root.resolve()
    now = time.monotonic()

    cached = _GITIGNORE_CACHE.get(root_resolved)
    if cached is not None:
        _ts, cached_specs = cached
        if now - _ts < _GITIGNORE_CACHE_TTL and _check_mtimes(cached_specs):
            _GITIGNORE_CACHE.move_to_end(root_resolved)
            return cached_specs

    from pathspec import PathSpec as _PS
    from pathspec.patterns.gitwildmatch import GitWildMatchPattern

    specs: _SpecEntry = []
    for parent in [root_resolved] + list(root_resolved.parents):
        gitignore = parent / ".gitignore"
        if gitignore.is_file():
            spec = _PS.from_lines(
                GitWildMatchPattern,
                gitignore.read_text(encoding="utf-8", errors="replace").splitlines(),
            )
            mtime = gitignore.stat().st_mtime
            specs.append((parent, spec, mtime))

    _GITIGNORE_CACHE[root_resolved] = (now, specs)
    _evict_if_full()

    return specs


def _check_mtimes(specs: _SpecEntry) -> bool:
    """Return True if every cached .gitignore file still has the same mtime."""
    for gitignore_dir, _, cached_mtime in specs:
        gitignore = gitignore_dir / ".gitignore"
        try:
            if gitignore.stat().st_mtime != cached_mtime:
                return False
        except OSError:
            return False
    return True


def _evict_if_full() -> None:
    """Evict the oldest (first-inserted) entry when the cache exceeds the limit."""
    if len(_GITIGNORE_CACHE) >= _GITIGNORE_CACHE_MAX:
        _GITIGNORE_CACHE.popitem(last=False)


# --- Public API ---------------------------------------------------------------


class GitignoreFilter:
    """Fast .gitignore-aware path filter with module-level caching.

    Usage::

        filt = GitignoreFilter(search_root)
        filt.is_ignored(Path("some/file.pyc"))
        filt.filter([Path("a.py"), Path("b.log")])
    """

    def __init__(self, search_root: Path, resolved: bool = False) -> None:
        """Bind the filter to *search_root*.

        Args:
            search_root: The root directory whose ``.gitignore`` (and parents')
                         rules should apply.
            resolved:    Set to True if *search_root* is already resolved
                         (avoids an extra ``Path.resolve()`` call).
        """
        self._root = search_root if resolved else search_root.resolve()
        self._specs = _load_gitignore_specs(self._root)

    def is_ignored(self, path: Path, resolved: bool = False) -> bool:
        """Return True if *path* matches any applicable .gitignore rule.

        Args:
            path:     The path to check.
            resolved: Set to True if *path* is already resolved
                      (avoids an extra ``Path.resolve()`` call).
        """
        p = path if resolved else path.resolve()
        for gitignore_dir, spec, _ in reversed(self._specs):
            try:
                rel = p.relative_to(gitignore_dir)
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
        """Filter *paths* to only those not ignored by .gitignore rules.

        When *include_ignored* is True, all paths are returned unchanged.
        """
        if include_ignored:
            return paths
        return [p for p in paths if not self.is_ignored(p)]
