from __future__ import annotations

import os
from pathlib import Path

from laffyhand.config import LaffyConfig


class WorkspaceService:
    def __init__(self, config: LaffyConfig) -> None:
        self._config = config

    def resolve_workspace(self) -> str:
        cfg = self._config.paths.workspace
        if cfg:
            return str(Path(cfg).resolve())
        return os.getcwd()


__all__ = ["WorkspaceService"]
