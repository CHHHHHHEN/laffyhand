from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS _schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS session (
    id              TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'active',
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
    metadata        TEXT NOT NULL DEFAULT '{}',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL,
    ended_at        REAL
);

CREATE TABLE IF NOT EXISTS message (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT,
    tool_call_id    TEXT,
    tool_name       TEXT,
    tool_args       TEXT,
    reasoning       TEXT,
    token_count     INTEGER,
    timestamp       REAL NOT NULL,
    turn_index      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_message_session ON message(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_session_status ON session(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_session_created ON session(created_at DESC);

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
    conn.executescript(DDL)
    conn.execute(
        "INSERT OR IGNORE INTO _schema_version (version) VALUES (?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()
