CREATE TABLE session_message (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    time_created INTEGER NOT NULL,
    time_updated INTEGER NOT NULL,
    data TEXT NOT NULL
);

CREATE INDEX idx_session_message_session_id ON session_message(session_id);
CREATE INDEX idx_session_message_session_id_type ON session_message(session_id, type);
CREATE INDEX idx_session_message_time_created ON session_message(time_created);
