from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel


class FileTag(BaseModel):
    path: str
    message: str
    tags: dict[str, str]
    updated_at: str


class FileTagRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def upsert(
        self,
        path: str,
        message: str | None = None,
        key: str | None = None,
        value: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get(path)
        tag_dict: dict[str, str] = {}
        new_message = message or ""
        if existing:
            new_message = message if message is not None else existing.message
            tag_dict = dict(existing.tags)
        if key is not None:
            tag_dict[key] = value or ""
        if existing:
            self._conn.execute(
                "UPDATE file_tag SET message=?, tags=?, updated_at=? WHERE path=?",
                (new_message, json.dumps(tag_dict), now, path),
            )
        else:
            self._conn.execute(
                "INSERT INTO file_tag (path, message, tags, updated_at) VALUES (?, ?, ?, ?)",
                (path, new_message, json.dumps(tag_dict), now),
            )

    def get(self, path: str) -> FileTag | None:
        row = self._conn.execute(
            "SELECT * FROM file_tag WHERE path=?", (path,)
        ).fetchone()
        if row is None:
            return None
        return FileTag(
            path=row["path"],
            message=row["message"],
            tags=json.loads(row["tags"]),
            updated_at=row["updated_at"],
        )

    def list_by_prefix(self, prefix: str) -> list[FileTag]:
        rows = self._conn.execute(
            "SELECT * FROM file_tag WHERE path >= ? AND path < ? ORDER BY path",
            (prefix, prefix + "\xff"),
        ).fetchall()
        return [
            FileTag(
                path=r["path"],
                message=r["message"],
                tags=json.loads(r["tags"]),
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def list_all(self) -> list[FileTag]:
        rows = self._conn.execute(
            "SELECT * FROM file_tag ORDER BY path"
        ).fetchall()
        return [
            FileTag(
                path=r["path"],
                message=r["message"],
                tags=json.loads(r["tags"]),
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def delete(self, path: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM file_tag WHERE path=?", (path,)
        ).fetchone()
        if row is None:
            return False
        self._conn.execute("DELETE FROM file_tag WHERE path=?", (path,))
        return True

    def delete_missing(self) -> int:
        rows = self._conn.execute("SELECT path FROM file_tag").fetchall()
        deleted = 0
        for row in rows:
            if not os.path.exists(row["path"]):
                self._conn.execute(
                    "DELETE FROM file_tag WHERE path=?", (row["path"],)
                )
                deleted += 1
        return deleted

    def get_all_paths(self) -> list[str]:
        rows = self._conn.execute("SELECT path FROM file_tag").fetchall()
        return [r["path"] for r in rows]
