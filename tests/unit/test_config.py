from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from laffyhand.config import (
    LaffyConfig,
    LLMConfig,
    DBConfig,
    LogConfig,
    AgentConfig,
    PathsConfig,
    MCPConfig,
    load_config,
    find_config,
    resolve_provider,
    resolve_model,
)


SAMPLE_PROVIDERS = {
    "test": {
        "type": "openai",
        "base_url": "http://test",
        "api_key": "key",
        "models": [{"name": "gpt-4", "context_size": 128000}],
    },
}

SAMPLE_LLM = {
    "default_provider": "test",
    "providers": SAMPLE_PROVIDERS,
}


class TestConfigModels:
    def test_llm_config_defaults(self):
        cfg = LLMConfig(**SAMPLE_LLM)
        assert cfg.default_provider == "test"
        assert "test" in cfg.providers
        assert cfg.providers["test"].type == "openai"
        assert cfg.providers["test"].models[0].name == "gpt-4"

    def test_resolve_provider(self):
        llm_cfg = LLMConfig(**SAMPLE_LLM)
        key, pc = resolve_provider(llm_cfg)
        assert key == "test"
        assert pc.type == "openai"

    def test_resolve_provider_missing(self):
        llm_cfg = LLMConfig(**SAMPLE_LLM)
        with pytest.raises(ValueError, match="not found"):
            resolve_provider(llm_cfg, "nonexistent")

    def test_resolve_model(self):
        llm_cfg = LLMConfig(**SAMPLE_LLM)
        _, pc = resolve_provider(llm_cfg)
        mc = resolve_model(pc)
        assert mc.name == "gpt-4"
        assert mc.context_size == 128000

    def test_resolve_model_by_name(self):
        llm_cfg = LLMConfig(**SAMPLE_LLM)
        _, pc = resolve_provider(llm_cfg)
        mc = resolve_model(pc, "gpt-4")
        assert mc.name == "gpt-4"

    def test_resolve_model_missing(self):
        llm_cfg = LLMConfig(**SAMPLE_LLM)
        _, pc = resolve_provider(llm_cfg)
        with pytest.raises(ValueError, match="not found"):
            resolve_model(pc, "nonexistent")

    def test_db_config_defaults(self):
        cfg = DBConfig()
        assert cfg.path == "./laffyhand.db"

    def test_log_config_defaults(self):
        cfg = LogConfig()
        assert cfg.dir == "logs"
        assert cfg.level == "INFO"
        assert cfg.retention_days == 10
        assert cfg.console is True

    def test_agent_config_defaults(self):
        cfg = AgentConfig()
        assert cfg.title_mode == "auto"
        assert cfg.compaction_tail_turns == 2
        assert cfg.max_steps == 50
        assert cfg.max_concurrent_subagents == 2

    def test_paths_config_defaults(self):
        cfg = PathsConfig()
        assert cfg.skills == []
        assert cfg.agents == []

    def test_mcp_config_defaults(self):
        cfg = MCPConfig()
        assert cfg.servers == {}

    def test_laffy_config_defaults(self):
        cfg = LaffyConfig(llm=LLMConfig(**SAMPLE_LLM))
        assert cfg.db.path == "./laffyhand.db"
        assert cfg.logging.level == "INFO"
        assert cfg.agent.max_steps == 50

    def test_laffy_config_minimal(self):
        cfg = LaffyConfig.model_validate({"llm": SAMPLE_LLM})
        assert cfg.llm.default_provider == "test"
        assert cfg.llm.providers["test"].base_url == "http://test"


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
        with tempfile.NamedTemporaryFile(suffix=".yml", mode="w", delete=False) as f:
            yaml.dump({"llm": SAMPLE_LLM}, f)
            fname = f.name
        try:
            found = find_config(fname)
            assert found == fname
        finally:
            os.unlink(fname)

    def test_find_config_default_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig = Path.cwd()
            os.chdir(tmp)
            try:
                with open("laffyhand.yml", "w") as f:
                    yaml.dump({"llm": SAMPLE_LLM}, f)
                result = find_config(None)
                assert result == "laffyhand.yml"
            finally:
                os.chdir(orig)

    def test_load_config_full(self):
        data = {
            "llm": SAMPLE_LLM,
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
            },
            "mcp": {
                "servers": {
                    "local-1": {
                        "type": "local",
                        "command": [
                            "npx",
                            "-y",
                            "@modelcontextprotocol/server-everything",
                        ],
                    },
                },
            },
        }
        with tempfile.NamedTemporaryFile(suffix=".yml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            fname = f.name
        try:
            cfg = load_config(fname)
            assert cfg.llm.default_provider == "test"
            assert cfg.llm.providers["test"].base_url == "http://test"
            assert cfg.llm.providers["test"].api_key == "key"
            assert cfg.llm.providers["test"].models[0].name == "gpt-4"
            assert cfg.llm.providers["test"].models[0].context_size == 128000
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
            assert "local-1" in cfg.mcp.servers
        finally:
            os.unlink(fname)

    def test_load_config_minimal(self):
        data = {"llm": SAMPLE_LLM}
        with tempfile.NamedTemporaryFile(suffix=".yml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            fname = f.name
        try:
            cfg = load_config(fname)
            assert cfg.llm.providers["test"].base_url == "http://test"
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

    def test_load_config_invalid_schema_bad_provider_type(self):
        data = {
            "llm": {
                "default_provider": "x",
                "providers": {
                    "x": {
                        "type": "unknown",
                        "base_url": "",
                        "api_key": "",
                        "models": [{"name": "m"}],
                    }
                },
            }
        }
        with tempfile.NamedTemporaryFile(suffix=".yml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            fname = f.name
        try:
            with pytest.raises(Exception):
                load_config(fname)
        finally:
            os.unlink(fname)
