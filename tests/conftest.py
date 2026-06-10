from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

from laffyhand.core.session import SessionManager
from laffyhand.db import SessionRepo, MessageRepo, create_tables
from laffyhand.config import LaffyConfig


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def db_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=5000")
    create_tables(conn)
    yield conn
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass
    conn.close()


_SAMPLE_PROVIDERS = {
    "test": {
        "type": "openai",
        "base_url": "http://test",
        "api_key": "test-key",
        "models": [{"name": "test-model", "context_size": 128000}],
    },
}


@pytest.fixture
def session_manager(db_conn: sqlite3.Connection) -> SessionManager:
    session_repo = SessionRepo(db_conn)
    message_repo = MessageRepo(db_conn)
    mgr = SessionManager(session_repo, message_repo, db_conn)
    yield mgr
    mgr.close()


@pytest.fixture
def runtime_config(db_path: str) -> LaffyConfig:
    return LaffyConfig.model_validate(
        {
            "llm": {
                "default_provider": "test",
                "providers": _SAMPLE_PROVIDERS,
            },
            "db": {"path": db_path},
        }
    )
