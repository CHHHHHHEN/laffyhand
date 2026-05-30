from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, Field

from laffyhand.agent.mcp.config import LocalMCPConfig, RemoteMCPConfig


class LLMConfig(BaseModel):
    base_url: str
    api_key: str
    model_name: str
    context_size: int = 1_000_000


class DBConfig(BaseModel):
    path: str = "./laffyhand.db"


class LogConfig(BaseModel):
    dir: str = "logs"
    level: str = "INFO"
    retention_days: int = 10
    console: bool = False


class AgentConfig(BaseModel):
    title_mode: Literal["off", "on_create", "on_compact", "auto"] = "on_compact"
    compaction_tail_turns: int = 2
    max_steps: int = 50
    max_concurrent_subagents: int = 2


class PathsConfig(BaseModel):
    skills: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    todos: str = ".todos.json"


class MCPConfig(BaseModel):
    servers: dict[
        str, Annotated[LocalMCPConfig | RemoteMCPConfig, Field(discriminator="type")]
    ] = Field(default_factory=dict)


class LaffyConfig(BaseModel):
    llm: LLMConfig
    db: DBConfig = DBConfig()
    logging: LogConfig = LogConfig()
    agent: AgentConfig = AgentConfig()
    paths: PathsConfig = PathsConfig()
    mcp: MCPConfig = MCPConfig()


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
