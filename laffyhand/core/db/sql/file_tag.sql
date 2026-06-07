CREATE TABLE IF NOT EXISTS file_tag (
    path            TEXT PRIMARY KEY,
    message         TEXT NOT NULL DEFAULT '',
    tags            TEXT NOT NULL DEFAULT '{}'
        CHECK (JSON_VALID(tags)),
    updated_at      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','stale')),
    exports         TEXT NOT NULL DEFAULT '{}'
        CHECK (JSON_VALID(exports)),
    side_effects    TEXT NOT NULL DEFAULT '',
    depends_on      TEXT NOT NULL DEFAULT '[]'
        CHECK (JSON_VALID(depends_on))
);
