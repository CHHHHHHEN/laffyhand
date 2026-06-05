from typing import Literal

from pydantic import BaseModel


class LocalMCPConfig(BaseModel):
    type: Literal["local"] = "local"
    command: list[str]
    env: dict[str, str] = {}
    timeout: int = 300


class RemoteMCPConfig(BaseModel):
    type: Literal["remote"] = "remote"
    url: str
    transport: Literal["sse", "streamable-http"] | None = None
    headers: dict[str, str] = {}
    timeout: int = 300


MCPConfig = LocalMCPConfig | RemoteMCPConfig
