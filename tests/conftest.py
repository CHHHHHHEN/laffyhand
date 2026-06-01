from __future__ import annotations

import os
import tempfile

import pytest

from laffyhand.agent.session import SessionManager
from laffyhand.config import LaffyConfig


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


_SAMPLE_PROVIDERS = {
    "test": {
        "type": "openai",
        "base_url": "http://test",
        "api_key": "test-key",
        "models": [{"name": "test-model", "context_size": 128000}],
    },
}


@pytest.fixture
def session_manager(db_path: str) -> SessionManager:
    return SessionManager(db_path)


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
