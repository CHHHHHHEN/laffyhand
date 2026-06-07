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

CREATE INDEX IF NOT EXISTS idx_session_status ON session(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_session_created ON session(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_parent ON session(parent_id);
CREATE INDEX IF NOT EXISTS idx_session_parent_status ON session(parent_id, status);
CREATE INDEX IF NOT EXISTS idx_session_fork ON session(fork_id);
