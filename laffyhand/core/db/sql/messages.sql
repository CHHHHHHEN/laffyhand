-- Messages belonging to a session, with polymorphic data payloads
CREATE TABLE IF NOT EXISTS session_message (
    id              TEXT PRIMARY KEY,                                  -- unique message ID
    session_id      TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE, -- owning session
    type            TEXT NOT NULL,                                     -- user|assistant|synthetic|shell|agent-switched|model-switched|compaction
    time_created    INTEGER NOT NULL,                                  -- Unix timestamp (ms)
    time_updated    INTEGER NOT NULL,                                  -- Unix timestamp (ms)
    data            TEXT NOT NULL                                      -- JSON payload matching type
);

CREATE INDEX IF NOT EXISTS idx_session_message_session ON session_message(session_id, time_created);
CREATE INDEX IF NOT EXISTS idx_session_message_type ON session_message(session_id, type);
