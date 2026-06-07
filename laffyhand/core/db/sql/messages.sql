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
