from __future__ import annotations

import importlib.resources
import sqlite3

from loguru import logger

SCHEMA_VERSION = 13

_SQL_FILES = [
    "schema_version.sql",
    "session.sql",
    "messages.sql",
    "todo.sql",
    "file_tag.sql",
]


def _load_core_ddl() -> str:
    parts: list[str] = []
    for name in _SQL_FILES:
        raw = importlib.resources.files(__package__).joinpath("sql", name).read_text()
        parts.append(raw.strip())
    return "\n\n".join(parts) + "\n"


CORE_DDL = _load_core_ddl()

_MIGRATIONS: dict[int, str] = {
    13: """
        -- Migrate session: rename agent_version -> agent_name
        ALTER TABLE session RENAME COLUMN agent_version TO agent_name;
    """,
    12: """
        -- Migrate file_tag: rename message -> content, drop unused columns (if old schema)
        CREATE TABLE IF NOT EXISTS file_tag_v2 (
            path        TEXT PRIMARY KEY,
            content     TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );
        INSERT INTO file_tag_v2 (path, content, updated_at)
            SELECT path, COALESCE(message, ''), updated_at FROM file_tag;
        DROP TABLE file_tag;
        ALTER TABLE file_tag_v2 RENAME TO file_tag;
    """,
    11: """
        CREATE TABLE IF NOT EXISTS todo_v2 (
            id              TEXT NOT NULL,
            session_id      TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
            content         TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','in_progress','completed','blocked')),
            depends_on      TEXT NOT NULL DEFAULT '[]',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            completed_at    TEXT,
            task_tool_id    TEXT,
            metadata        TEXT NOT NULL DEFAULT '{}'
                CHECK (JSON_VALID(metadata)),
            PRIMARY KEY (session_id, id)
        );
        INSERT INTO todo_v2 SELECT * FROM todo;
        DROP TABLE todo;
        ALTER TABLE todo_v2 RENAME TO todo;
        CREATE INDEX IF NOT EXISTS idx_todo_session ON todo(session_id, status);
        CREATE INDEX IF NOT EXISTS idx_todo_task_tool ON todo(task_tool_id);
    """,
    7: """
        ALTER TABLE session ADD COLUMN cost INTEGER NOT NULL DEFAULT 0;
    """,
    6: """
        ALTER TABLE session ADD COLUMN cache_write_tokens INTEGER NOT NULL DEFAULT 0;
    """,
    5: """
        -- Migrate from old message table to session_message table
        INSERT OR IGNORE INTO session_message (id, session_id, type, time_created, time_updated, data)
        SELECT
            printf('migrated_%d', m.id),
            m.session_id,
            CASE m.role
                WHEN 'system' THEN 'synthetic'
                WHEN 'user' THEN 'user'
                WHEN 'assistant' THEN 'assistant'
                WHEN 'tool' THEN 'shell'
            END,
            CAST(strftime('%s', m.timestamp) AS INTEGER),
            CAST(strftime('%s', m.timestamp) AS INTEGER),
            CASE m.role
                WHEN 'system' THEN json_object('sessionID', m.session_id, 'text', COALESCE(m.content, ''))
                WHEN 'user' THEN json_object('text', COALESCE(m.content, ''), 'files', json_array(), 'agents', json_array(), 'references', json_array())
                WHEN 'assistant' THEN json_object(
                    'agent', '',
                    'model', json_object('id', '', 'provider', ''),
                    'content', CASE
                        WHEN m.reasoning IS NOT NULL AND m.content IS NOT NULL THEN
                            json_array(json_object('type', 'reasoning', 'id', printf('reasoning_%d', m.id), 'text', m.reasoning), json_object('type', 'text', 'text', m.content))
                        WHEN m.reasoning IS NOT NULL THEN
                            json_array(json_object('type', 'reasoning', 'id', printf('reasoning_%d', m.id), 'text', m.reasoning))
                        WHEN m.content IS NOT NULL THEN
                            json_array(json_object('type', 'text', 'text', m.content))
                        ELSE json_array()
                    END,
                    'snapshot', json_object(),
                    'finish', 'stop',
                    'cost', 0
                )
                WHEN 'tool' THEN json_object(
                    'callID', COALESCE(m.tool_call_id, printf('migrated_%d', m.id)),
                    'command', '',
                    'output', COALESCE(m.content, ''),
                    'truncated', false,
                    'time', json_object('created', CAST(strftime('%s', m.timestamp) AS INTEGER))
                )
            END
        FROM message m
        WHERE NOT EXISTS (SELECT 1 FROM session_message sm WHERE sm.session_id = m.session_id);
    """,
}


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(CORE_DDL)
    migrate(conn)
    conn.commit()


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
