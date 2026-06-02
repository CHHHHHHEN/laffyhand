from __future__ import annotations

import sqlite3

from loguru import logger

SCHEMA_VERSION = 4

CORE_DDL = """
CREATE TABLE IF NOT EXISTS _schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS session (
    id              TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active','completed','archived')),
    title           TEXT NOT NULL DEFAULT '',
    cwd             TEXT NOT NULL DEFAULT '',
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    agent_version   TEXT NOT NULL DEFAULT '',
    turn_count      INTEGER NOT NULL DEFAULT 0,
    step_count      INTEGER NOT NULL DEFAULT 0,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost            INTEGER NOT NULL DEFAULT 0,
    parent_id       TEXT REFERENCES session(id),
    fork_id         TEXT REFERENCES session(id),
    message_count   INTEGER NOT NULL DEFAULT 0,
    summary         TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}'
        CHECK(JSON_VALID(metadata)),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    ended_at        TEXT
);

CREATE TABLE IF NOT EXISTS session_message (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    type            TEXT NOT NULL,
    time_created    INTEGER NOT NULL,
    time_updated    INTEGER NOT NULL,
    data            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_session_message_session ON session_message(session_id, time_created);
CREATE INDEX IF NOT EXISTS idx_session_message_type ON session_message(session_id, type);
CREATE INDEX IF NOT EXISTS idx_session_status ON session(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_session_created ON session(created_at DESC);

CREATE TABLE IF NOT EXISTS todo (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','in_progress','completed','cancelled','blocked')),
    priority        TEXT NOT NULL DEFAULT 'medium'
        CHECK (priority IN ('high','medium','low')),
    depends_on      TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    completed_at    TEXT,
    task_tool_id    TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}'
        CHECK (JSON_VALID(metadata))
);

CREATE INDEX IF NOT EXISTS idx_todo_session ON todo(session_id, status);
"""


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(CORE_DDL)
    migrate(conn)
    conn.commit()


def has_fts5(conn: sqlite3.Connection) -> bool:
    return False


_MIGRATIONS: dict[int, str] = {}


def migrate(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM _schema_version",
    ).fetchone()
    current = row[0] if row[0] else 0

    for version in range(current + 1, SCHEMA_VERSION + 1):
        if version in _MIGRATIONS:
            logger.info(f"Running migration to version {version}")
            try:
                conn.executescript(_MIGRATIONS[version])
            except sqlite3.OperationalError as e:
                logger.warning(
                    f"Migration v{version} skipped (may already be applied): {e}"
                )
        conn.execute(
            "INSERT OR IGNORE INTO _schema_version (version) VALUES (?)",
            (version,),
        )
