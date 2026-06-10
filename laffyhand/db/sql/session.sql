-- Core session table: tracks conversation lifecycle, token usage, and lineage
CREATE TABLE IF NOT EXISTS session (
    id              TEXT PRIMARY KEY,                                  -- unique session ID
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active','archived')),                     -- active | archived
    title           TEXT NOT NULL DEFAULT '',                  -- user-visible title
    cwd             TEXT NOT NULL DEFAULT '',                  -- working directory at creation
    provider        TEXT NOT NULL,                                     -- LLM provider ID
    model           TEXT NOT NULL,                                     -- LLM model ID
    agent_name      TEXT NOT NULL DEFAULT '',                 -- agent name (build, chat, etc.)
    turn_count      INTEGER NOT NULL DEFAULT 0,                       -- LLM request-response rounds
    step_count      INTEGER NOT NULL DEFAULT 0,                       -- agent loop iterations
    input_tokens    INTEGER NOT NULL DEFAULT 0,                       -- cumulative input tokens
    output_tokens   INTEGER NOT NULL DEFAULT 0,                       -- cumulative output tokens
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,                      -- cumulative reasoning tokens
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,                     -- cumulative cache-read tokens
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,                    -- cumulative cache-write tokens
    parent_id       TEXT REFERENCES session(id),                      -- parent session (compaction chain)
    message_count   INTEGER NOT NULL DEFAULT 0,                       -- number of messages
    metadata        TEXT NOT NULL DEFAULT '{}'
        CHECK(JSON_VALID(metadata)),                                  -- extensible metadata (JSON)
    created_at      TEXT NOT NULL,                                     -- ISO-8601 timestamp
    updated_at      TEXT NOT NULL                                      -- ISO-8601 timestamp
);

CREATE INDEX IF NOT EXISTS idx_session_status ON session(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_session_created ON session(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_parent ON session(parent_id);
CREATE INDEX IF NOT EXISTS idx_session_parent_status ON session(parent_id, status);
