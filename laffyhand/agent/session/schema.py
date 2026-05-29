from __future__ import annotations

import sqlite3

from loguru import logger

SCHEMA_VERSION = 2

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
    model           TEXT NOT NULL DEFAULT '',
    agent_version   TEXT NOT NULL DEFAULT '',
    turn_count      INTEGER NOT NULL DEFAULT 0,
    step_count      INTEGER NOT NULL DEFAULT 0,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS message (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    role            TEXT NOT NULL
        CHECK(role IN ('system','user','assistant','tool')),
    content         TEXT,
    tool_call_id    TEXT,
    tool_name       TEXT,
    tool_args       TEXT,
    reasoning       TEXT,
    token_count     INTEGER,
    timestamp       TEXT NOT NULL,
    turn_index      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_message_session ON message(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_session_status ON session(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_session_created ON session(created_at DESC);
"""

FTS5_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
    content, reasoning
);

CREATE TRIGGER IF NOT EXISTS message_fts_ai AFTER INSERT ON message BEGIN
    INSERT INTO message_fts(rowid, content, reasoning)
    VALUES (new.id, new.content, new.reasoning);
END;

CREATE TRIGGER IF NOT EXISTS message_fts_ad AFTER DELETE ON message BEGIN
    DELETE FROM message_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS message_fts_au AFTER UPDATE ON message BEGIN
    DELETE FROM message_fts WHERE rowid = old.id;
    INSERT INTO message_fts(rowid, content, reasoning)
    VALUES (new.id, new.content, new.reasoning);
END;
"""


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(CORE_DDL)
    try:
        conn.executescript(FTS5_DDL)
    except sqlite3.OperationalError as e:
        logger.warning(f"FTS5 not available, full-text search disabled: {e}")
    migrate(conn)
    conn.commit()


def has_fts5(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT count(*) FROM message_fts LIMIT 0")
        return True
    except sqlite3.OperationalError:
        return False


_MIGRATIONS: dict[int, str] = {
    2: """
        -- Convert timestamp columns from REAL (Unix epoch) to TEXT (ISO 8601).
        -- SQLite's flexible typing allows in-place update.
        UPDATE session SET
            created_at = datetime(created_at, 'unixepoch'),
            updated_at = datetime(updated_at, 'unixepoch'),
            ended_at = CASE WHEN ended_at IS NOT NULL THEN datetime(ended_at, 'unixepoch') ELSE NULL END
        WHERE created_at GLOB '[0-9]*';

        UPDATE message SET
            timestamp = datetime(timestamp, 'unixepoch')
        WHERE timestamp GLOB '[0-9]*';
    """,
}


def migrate(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM _schema_version",
    ).fetchone()
    current = row[0] if row[0] else 0

    for version in range(current + 1, SCHEMA_VERSION + 1):
        if version in _MIGRATIONS:
            logger.info(f"Running migration to version {version}")
            conn.executescript(_MIGRATIONS[version])
        conn.execute(
            "INSERT OR IGNORE INTO _schema_version (version) VALUES (?)",
            (version,),
        )
