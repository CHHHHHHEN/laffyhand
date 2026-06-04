from __future__ import annotations

from pathlib import Path


def is_within(path: str | Path, workspace: str | Path | None) -> bool:
    if workspace is None:
        return True
    workspace_resolved = Path(workspace).resolve()
    path_resolved = Path(path).resolve()
    try:
        path_resolved.relative_to(workspace_resolved)
        return True
    except ValueError:
        return False
