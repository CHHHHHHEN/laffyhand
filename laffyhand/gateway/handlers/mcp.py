from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from laffyhand.core.runtime import AgentRuntime
    from laffyhand.gateway.transport import Transport


async def handle_mcp_status(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    status = runtime.mcp_service.get_status()
    logger.debug(f"mcp/status: returning {len(status)} server(s) (conn={conn_id})")
    return {
        "servers": [{"name": name, "status": st} for name, st in status.items()],
    }


async def handle_mcp_add_server(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    name: str = params.get("name", "")
    if not name:
        raise ValueError("name is required")
    from laffyhand.config import LocalMCPConfig, RemoteMCPConfig
    from laffyhand.config import MCPConfig as MCPCfg

    server_type: str = params.get("type", "local")
    if server_type == "local":
        command: list[str] = params.get("command", [])
        if not command:
            raise ValueError("command is required for local MCP servers")
        cfg: MCPCfg = LocalMCPConfig(command=command, env=params.get("env", {}), timeout=params.get("timeout", 300))
    elif server_type == "remote":
        url: str = params.get("url", "")
        if not url:
            raise ValueError("url is required for remote MCP servers")
        cfg = RemoteMCPConfig(url=url, transport=params.get("transport"), headers=params.get("headers", {}), timeout=params.get("timeout", 300))
    else:
        raise ValueError(f"Invalid MCP server type: {server_type}")
    try:
        tool_names = await runtime.add_mcp_server(name, cfg)
        return {"status": "connected", "name": name, "tools": tool_names}
    except Exception as e:
        logger.error(f"Failed to add MCP server '{name}': {e}")
        raise ValueError(f"Failed to connect MCP server: {e}")


async def handle_mcp_remove_server(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    name: str = params.get("name", "")
    if not name:
        raise ValueError("name is required")
    count = await runtime.remove_mcp_server(name)
    return {"status": "disconnected", "name": name, "unregistered_tools": count}
