from __future__ import annotations

import os
import tempfile

import pytest

from laffyhand.agent.session import SessionManager
from laffyhand.config import LaffyConfig, LLMConfig


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def session_manager(db_path: str) -> SessionManager:
    return SessionManager(db_path)


@pytest.fixture
def runtime_config() -> LaffyConfig:
    return LaffyConfig.model_construct(
        llm=LLMConfig(
            base_url="http://test",
            api_key="test-key",
            model_name="test-model",
            context_size=128000,
        ),
    )
