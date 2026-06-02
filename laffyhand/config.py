from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from laffyhand.agent.mcp.config import LocalMCPConfig, RemoteMCPConfig


class ModelConfig(BaseModel):
    name: str
    context_size: int = 128_000


ProviderType = Literal["openai", "deepseek"]


class ProviderConfig(BaseModel):
    type: ProviderType
    base_url: str
    api_key: str
    models: list[ModelConfig] = Field(min_length=1)


class LLMConfig(BaseModel):
    default_provider: str = ""
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)


class DBConfig(BaseModel):
    path: str = "./laffyhand.db"


class LogConfig(BaseModel):
    dir: str = "logs"
    level: str = "INFO"
    retention_days: int = 10
    console: bool = False


class AgentConfig(BaseModel):
    title_mode: Literal["off", "on_create", "on_compact", "auto"] = "auto"
    compaction_tail_turns: int = 2
    max_steps: int = 50
    max_concurrent_subagents: int = 2


class PathsConfig(BaseModel):
    skills: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)


class MCPConfig(BaseModel):
    servers: dict[
        str, Annotated[LocalMCPConfig | RemoteMCPConfig, Field(discriminator="type")]
    ] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_none(cls, data: Any) -> Any:
        if data is None:
            return {}
        if isinstance(data, dict) and data.get("servers") is None:
            data["servers"] = {}
        return data


class LaffyConfig(BaseModel):
    llm: LLMConfig
    db: DBConfig = DBConfig()
    logging: LogConfig = LogConfig()
    agent: AgentConfig = AgentConfig()
    paths: PathsConfig = PathsConfig()
    mcp: MCPConfig = MCPConfig()


def resolve_provider(
    llm_cfg: LLMConfig, provider: str | None = None
) -> tuple[str, ProviderConfig]:
    key = provider or llm_cfg.default_provider
    if not key:
        raise ValueError("No provider selected. Set llm.default_provider in config.")
    cfg = llm_cfg.providers.get(key)
    if cfg is None:
        raise ValueError(
            f"Provider {key!r} not found in llm.providers. "
            f"Available: {list(llm_cfg.providers)}"
        )
    return key, cfg


def resolve_model(
    provider_cfg: ProviderConfig, model: str | None = None
) -> ModelConfig:
    if model:
        for m in provider_cfg.models:
            if m.name == model:
                return m
        names = [m.name for m in provider_cfg.models]
        raise ValueError(f"Model {model!r} not found in provider. Available: {names}")
    return provider_cfg.models[0]


def find_config(config_path: str | None) -> str | None:
    if config_path:
        return config_path if os.path.isfile(config_path) else None
    for candidate in ("laffyhand.yml", "laffyhand.yaml"):
        if os.path.isfile(candidate):
            return candidate
    return None


def load_config(config_path: str | None = None) -> LaffyConfig:
    found = find_config(config_path)
    if found is None:
        raise FileNotFoundError(
            "No configuration file found. "
            "Create laffyhand.yml in the current directory "
            "or pass --config <path>."
        )
    path = Path(found)
    with open(path) as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    return LaffyConfig.model_validate(raw)
