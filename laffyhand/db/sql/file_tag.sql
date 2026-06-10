-- Per-file semantic tags for context annotation across sessions
CREATE TABLE IF NOT EXISTS file_tag (
    path            TEXT PRIMARY KEY,                                  -- absolute file path
    content         TEXT NOT NULL,                                     -- semantic description
    updated_at      TEXT NOT NULL                                      -- ISO-8601 timestamp
);
