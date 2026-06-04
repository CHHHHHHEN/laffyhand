from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from pydantic import BaseModel


class FileTag(BaseModel):
    path: str
    message: str
    tags: dict[str, str]
    updated_at: str
    status: str = "active"
    exports: dict[str, str] = {}
    side_effects: str = ""
    depends_on: list[str] = []


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
        status: str | None = None,
        exports: dict[str, str] | None = None,
        side_effects: str | None = None,
        depends_on: list[str] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get(path)
        tag_dict: dict[str, str] = {}
        new_message = message or ""
        new_status = status or "active"
        new_exports: dict[str, str] = {}
        new_side_effects = ""
        new_depends_on: list[str] = []
        if existing:
            new_message = message if message is not None else existing.message
            tag_dict = dict(existing.tags)
            if status is None:
                new_status = existing.status
            new_exports = dict(existing.exports) if exports is None else exports
            new_side_effects = existing.side_effects if side_effects is None else side_effects
            new_depends_on = list(existing.depends_on) if depends_on is None else depends_on
        else:
            if exports is not None:
                new_exports = exports
            if side_effects is not None:
                new_side_effects = side_effects
            if depends_on is not None:
                new_depends_on = depends_on
        if key is not None:
            tag_dict[key] = value or ""
        if existing:
            self._conn.execute(
                "UPDATE file_tag SET message=?, tags=?, updated_at=?, status=?, exports=?, side_effects=?, depends_on=? WHERE path=?",
                (new_message, json.dumps(tag_dict), now, new_status, json.dumps(new_exports), new_side_effects, json.dumps(new_depends_on), path),
            )
        else:
            self._conn.execute(
                "INSERT INTO file_tag (path, message, tags, updated_at, status, exports, side_effects, depends_on) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (path, new_message, json.dumps(tag_dict), now, new_status, json.dumps(new_exports), new_side_effects, json.dumps(new_depends_on)),
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
            status=row["status"],
            exports=json.loads(row["exports"]) if row["exports"] else {},
            side_effects=row["side_effects"],
            depends_on=json.loads(row["depends_on"]) if row["depends_on"] else [],
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
                status=r["status"],
                exports=json.loads(r["exports"]) if r["exports"] else {},
                side_effects=r["side_effects"],
                depends_on=json.loads(r["depends_on"]) if r["depends_on"] else [],
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
                status=r["status"],
                exports=json.loads(r["exports"]) if r["exports"] else {},
                side_effects=r["side_effects"],
                depends_on=json.loads(r["depends_on"]) if r["depends_on"] else [],
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
        rows = self._conn.execute("SELECT path, status FROM file_tag WHERE status='active'").fetchall()
        deleted = 0
        for row in rows:
            if not os.path.exists(row["path"]):
                self._conn.execute(
                    "DELETE FROM file_tag WHERE path=?", (row["path"],)
                )
                deleted += 1
        return deleted

    def mark_stale_missing(self) -> int:
        """Mark tags as stale when their file no longer exists. Returns count marked."""
        rows = self._conn.execute(
            "SELECT path FROM file_tag WHERE status='active'"
        ).fetchall()
        marked = 0
        for row in rows:
            if not os.path.exists(row["path"]):
                self._conn.execute(
                    "UPDATE file_tag SET status='stale', updated_at=? WHERE path=?",
                    (datetime.now(timezone.utc).isoformat(), row["path"]),
                )
                marked += 1
        return marked

    def mark_stale(self, path: str) -> bool:
        """Mark a single tag as stale. Returns True if changed."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "UPDATE file_tag SET status='stale', updated_at=? WHERE path=? AND status='active'",
            (now, path),
        )
        return cursor.rowcount > 0

    def list_by_status(self, status: str) -> list[FileTag]:
        rows = self._conn.execute(
            "SELECT * FROM file_tag WHERE status=? ORDER BY path", (status,)
        ).fetchall()
        return [
            FileTag(
                path=r["path"],
                message=r["message"],
                tags=json.loads(r["tags"]),
                updated_at=r["updated_at"],
                status=r["status"],
                exports=json.loads(r["exports"]) if r["exports"] else {},
                side_effects=r["side_effects"],
                depends_on=json.loads(r["depends_on"]) if r["depends_on"] else [],
            )
            for r in rows
        ]

    def get_all_paths(self) -> list[str]:
        rows = self._conn.execute("SELECT path FROM file_tag").fetchall()
        return [r["path"] for r in rows]
