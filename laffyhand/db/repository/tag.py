from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from laffyhand.core.models.tag import FileTag


def _row_to_tag(row: sqlite3.Row) -> FileTag:
    return FileTag(
        path=row["path"],
        content=row["content"],
        updated_at=row["updated_at"],
    )


def _rows_to_tags(rows: list[sqlite3.Row]) -> list[FileTag]:
    return [_row_to_tag(r) for r in rows]


class FileTagRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def commit(self) -> None:
        self._conn.commit()

    def upsert(self, path: str, content: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO file_tag (path, content, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at",
            (path, content, now),
        )

    def get(self, path: str) -> FileTag | None:
        row = self._conn.execute(
            "SELECT * FROM file_tag WHERE path=?", (path,)
        ).fetchone()
        return _row_to_tag(row) if row else None

    def list_by_prefix(self, prefix: str) -> list[FileTag]:
        rows = self._conn.execute(
            "SELECT * FROM file_tag WHERE path >= ? AND path < ? ORDER BY path",
            (prefix, prefix + "\xff"),
        ).fetchall()
        return _rows_to_tags(rows)

    def list_all(self) -> list[FileTag]:
        rows = self._conn.execute("SELECT * FROM file_tag ORDER BY path").fetchall()
        return _rows_to_tags(rows)

    def delete(self, path: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM file_tag WHERE path=?", (path,)
        ).fetchone()
        if row is None:
            return False
        self._conn.execute("DELETE FROM file_tag WHERE path=?", (path,))
        return True
