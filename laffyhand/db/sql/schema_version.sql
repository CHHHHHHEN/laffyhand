-- Schema version tracking for incremental migrations
CREATE TABLE IF NOT EXISTS _schema_version (
    version INTEGER PRIMARY KEY               -- current schema version
);
