"""Workspace boundary check for path traversal prevention.

Provides ``is_within()`` to verify that a path falls under a given
workspace root, preventing directory-traversal attacks.
"""

from __future__ import annotations

from pathlib import Path


def is_within(path: str | Path, workspace: str | Path | None) -> bool:
    """Return True when *path* is inside (or equal to) *workspace*.

    A ``None`` workspace allows any path (disabled boundary check).
    Both arguments are resolved before comparison.
    """
    if workspace is None:
        return True
    workspace_resolved = Path(workspace).resolve()
    path_resolved = Path(path).resolve()
    try:
        path_resolved.relative_to(workspace_resolved)
        return True
    except ValueError:
        return False
