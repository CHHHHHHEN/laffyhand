from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from laffyhand.config import (
    LaffyConfig, LLMConfig, DBConfig, LogConfig, AgentConfig,
    PathsConfig, MCPConfig, load_config, find_config,
)


class TestConfigModels:
    def test_llm_config_defaults(self):
        cfg = LLMConfig(base_url="http://test", api_key="key", model_name="m")
        assert cfg.base_url == "http://test"
        assert cfg.api_key == "key"
        assert cfg.model_name == "m"
        assert cfg.context_size == 1_000_000

    def test_db_config_defaults(self):
        cfg = DBConfig()
        assert cfg.path == "./laffyhand.db"

    def test_log_config_defaults(self):
        cfg = LogConfig()
        assert cfg.dir == "logs"
        assert cfg.level == "INFO"
        assert cfg.retention_days == 10
        assert cfg.console is False

    def test_agent_config_defaults(self):
        cfg = AgentConfig()
        assert cfg.title_mode == "on_compact"
        assert cfg.compaction_tail_turns == 2
        assert cfg.max_steps == 50
        assert cfg.max_concurrent_subagents == 2

    def test_paths_config_defaults(self):
        cfg = PathsConfig()
        assert cfg.skills == []
        assert cfg.agents == []
        assert cfg.todos == ".todos.json"

    def test_mcp_config_defaults(self):
        cfg = MCPConfig()
        assert cfg.servers == {}

    def test_laffy_config_defaults(self):
        cfg = LaffyConfig(
            llm=LLMConfig(base_url="http://test", api_key="key", model_name="m"),
        )
        assert cfg.db.path == "./laffyhand.db"
        assert cfg.logging.level == "INFO"
        assert cfg.agent.max_steps == 50

    def test_laffy_config_minimal(self):
        cfg = LaffyConfig.model_validate({
            "llm": {"base_url": "http://test", "api_key": "key", "model_name": "m"},
        })
        assert cfg.llm.base_url == "http://test"


class TestLoadConfig:
    def test_find_config_none_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig = Path.cwd()
            os.chdir(tmp)
            try:
                result = find_config(None)
                assert result is None
            finally:
                os.chdir(orig)

    def test_find_config_explicit_path(self):
        with tempfile.NamedTemporaryFile(suffix=".yml", delete=False) as f:
            f.write(b"llm:\n  base_url: http://test\n  api_key: key\n  model_name: m\n")
            found = find_config(f.name)
            assert found == f.name
            os.unlink(f.name)

    def test_find_config_default_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig = Path.cwd()
            os.chdir(tmp)
            try:
                Path("laffyhand.yml").write_text(
                    "llm:\n  base_url: http://test\n  api_key: key\n  model_name: m\n"
                )
                result = find_config(None)
                assert result == "laffyhand.yml"
            finally:
                os.chdir(orig)

    def test_load_config_full(self):
        data = {
            "llm": {
                "base_url": "http://test",
                "api_key": "sk-test",
                "model_name": "gpt-4",
                "context_size": 128000,
            },
            "db": {"path": "/tmp/test.db"},
            "logging": {
                "dir": "/tmp/logs",
                "level": "DEBUG",
                "retention_days": 7,
                "console": True,
            },
            "agent": {
                "title_mode": "auto",
                "compaction_tail_turns": 3,
                "max_steps": 100,
                "max_concurrent_subagents": 5,
            },
            "paths": {
                "skills": ["skills/", "custom/"],
                "agents": ["agents/"],
                "todos": "/tmp/todos.json",
            },
            "mcp": {
                "servers": {
                    "local-1": {
                        "type": "local",
                        "command": ["npx", "-y", "@modelcontextprotocol/server-everything"],
                    },
                },
            },
        }
        with tempfile.NamedTemporaryFile(suffix=".yml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            fname = f.name
        try:
            cfg = load_config(fname)
            assert cfg.llm.base_url == "http://test"
            assert cfg.llm.api_key == "sk-test"
            assert cfg.llm.model_name == "gpt-4"
            assert cfg.llm.context_size == 128000
            assert cfg.db.path == "/tmp/test.db"
            assert cfg.logging.level == "DEBUG"
            assert cfg.logging.retention_days == 7
            assert cfg.logging.console is True
            assert cfg.agent.title_mode == "auto"
            assert cfg.agent.compaction_tail_turns == 3
            assert cfg.agent.max_steps == 100
            assert cfg.agent.max_concurrent_subagents == 5
            assert cfg.paths.skills == ["skills/", "custom/"]
            assert cfg.paths.agents == ["agents/"]
            assert cfg.paths.todos == "/tmp/todos.json"
            assert "local-1" in cfg.mcp.servers
        finally:
            os.unlink(fname)

    def test_load_config_minimal(self):
        data = {
            "llm": {
                "base_url": "http://test",
                "api_key": "sk-test",
                "model_name": "gpt-4",
            },
        }
        with tempfile.NamedTemporaryFile(suffix=".yml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            fname = f.name
        try:
            cfg = load_config(fname)
            assert cfg.llm.base_url == "http://test"
            assert cfg.db.path == "./laffyhand.db"
        finally:
            os.unlink(fname)

    def test_load_config_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yml")

    def test_load_config_invalid_yaml(self):
        with tempfile.NamedTemporaryFile(suffix=".yml", mode="w", delete=False) as f:
            f.write("llm: [invalid: yaml: broken")
            fname = f.name
        try:
            with pytest.raises(Exception):
                load_config(fname)
        finally:
            os.unlink(fname)

    def test_load_config_invalid_schema(self):
        data = {"llm": {"base_url": "http://test"}}  # missing api_key and model_name
        with tempfile.NamedTemporaryFile(suffix=".yml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            fname = f.name
        try:
            with pytest.raises(Exception):
                load_config(fname)
        finally:
            os.unlink(fname)
