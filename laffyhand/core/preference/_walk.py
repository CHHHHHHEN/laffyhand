from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path


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
