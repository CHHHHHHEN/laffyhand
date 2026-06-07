CREATE TABLE IF NOT EXISTS todo (
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

CREATE INDEX IF NOT EXISTS idx_todo_session ON todo(session_id, status);
CREATE INDEX IF NOT EXISTS idx_todo_task_tool ON todo(task_tool_id);
