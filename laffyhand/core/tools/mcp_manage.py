from __future__ import annotations

from typing import TYPE_CHECKING, Any

import urllib.parse

from loguru import logger

from laffyhand.config import LocalMCPConfig, RemoteMCPConfig
from laffyhand.core.mcp.service import MCPWrappedTool
from laffyhand.core.tools.base import BaseTool

_ALLOWED_MCP_COMMANDS: frozenset[str] = frozenset(
    {
        "npx",
        "uv",
        "uvx",
        "python",
        "python3",
        "node",
        "deno",
        "bun",
    }
)

if TYPE_CHECKING:
    from laffyhand.core.mcp import MCPService
    from laffyhand.core.tools.registry import ToolRegistry


class MCPListTool(BaseTool):
    name = "mcp_list"
    description = "List all MCP server connections and their status."

    def __init__(self, mcp_service: MCPService) -> None:
        super().__init__()
        self._mcp_service = mcp_service

    def _input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def run(self, params: dict[str, Any]) -> str:
        statuses = self._mcp_service.get_status()
        if not statuses:
            return "No MCP servers configured or connected."

        lines = ["## MCP Servers"]
        for name, status in statuses.items():
            lines.append(f"- **{name}**: {status}")
        return "\n".join(lines)


class MCPConnectTool(BaseTool):
    name = "mcp_connect"
    description = "Connect to a new MCP server at runtime and register its tools."

    def __init__(self, mcp_service: MCPService, tool_registry: ToolRegistry) -> None:
        super().__init__()
        self._mcp_service = mcp_service
        self._tool_registry = tool_registry

    def _input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "A unique name for this MCP server",
                },
                "url": {
                    "type": "string",
                    "description": "URL of the remote MCP server (required for remote servers, e.g. https://example.com/mcp)",
                },
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": 'Command and arguments for a local MCP server (e.g. ["npx", "-y", "@modelcontextprotocol/server-everything"])',
                },
                "transport": {
                    "type": "string",
                    "enum": ["sse", "streamable-http"],
                    "description": "Transport for remote servers (default: auto-detect)",
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers for remote MCP servers",
                },
            },
            "required": ["name"],
        }

    async def run(self, params: dict[str, Any]) -> str:
        name = params["name"]

        if self._mcp_service.get_client(name) is not None:
            return f"MCP server '{name}' is already connected."

        command = params.get("command")
        url = params.get("url")

        if url:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in ("https",):
                return "Only https:// URLs are allowed for remote MCP servers"
            host = parsed.hostname or ""
            # Block private/internal IP ranges
            import ipaddress

            try:
                addr = ipaddress.ip_address(host)
                if addr.is_private or addr.is_loopback or addr.is_link_local:
                    return "Connecting to private/internal IP addresses is not allowed"
            except ValueError:
                pass  # hostname, not IP - OK
            if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                return "Connecting to localhost is not allowed"

        if command:
            if not command or command[0] not in _ALLOWED_MCP_COMMANDS:
                allowed = ", ".join(sorted(_ALLOWED_MCP_COMMANDS))
                return (
                    f"Command '{command[0] if command else ''}' is not allowed. "
                    f"Allowed commands: {allowed}"
                )
            # Argument validation to prevent inline code execution
            args = command[1:]
            executable = command[0]
            if executable in ("python", "python3") and "-c" in args:
                return f"Using '-c' with {executable} is not allowed (inline code execution)"
            if executable == "node" and "-e" in args:
                return "Using '-e' with node is not allowed (inline code execution)"
            if executable == "deno" and "eval" in args:
                return "Using 'eval' with deno is not allowed (inline code execution)"
            # Block shell metacharacters in args
            import re

            if any(re.search(r"[;|`$()]", arg) for arg in args):
                return "Arguments contain shell metacharacters which are not allowed"
            cfg: LocalMCPConfig | RemoteMCPConfig = LocalMCPConfig(
                command=command,
            )
        elif url:
            cfg = RemoteMCPConfig(
                url=url,
                transport=params.get("transport"),
                headers=params.get("headers", {}),
            )
        else:
            return "Either 'url' (remote) or 'command' (local) must be provided."

        try:
            tool_defs = await self._mcp_service.connect_server(name, cfg)
        except Exception as e:
            logger.error(f"MCP '{name}' connection failed: {e}")
            return f"Failed to connect to MCP server '{name}': connection failed"

        # Register discovered tools with the tool registry
        for td in tool_defs:
            wrapper = MCPWrappedTool(name, td, self._mcp_service)
            self._tool_registry.register_tool(wrapper)
            logger.info(f"MCP tool registered: mcp_{name}_{td.name}")

        tool_names = [f"mcp_{name}_{td.name}" for td in tool_defs]
        return (
            f"Connected to MCP server '{name}' and registered {len(tool_defs)} tool(s): "
            f"{', '.join(tool_names)}"
        )


class MCPDisconnectTool(BaseTool):
    name = "mcp_disconnect"
    description = "Disconnect a running MCP server and unregister its tools."

    def __init__(self, mcp_service: MCPService, tool_registry: ToolRegistry) -> None:
        super().__init__()
        self._mcp_service = mcp_service
        self._tool_registry = tool_registry

    def _input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the MCP server to disconnect",
                },
            },
            "required": ["name"],
        }

    async def run(self, params: dict[str, Any]) -> str:
        name = params["name"]
        if self._mcp_service.get_client(name) is None:
            return f"MCP server '{name}' is not connected."

        # Unregister tools from this server
        prefix = f"mcp_{name}_"
        unregistered = self._tool_registry.unregister_by_prefix(prefix)

        await self._mcp_service.disconnect(name)
        return (
            f"Disconnected MCP server '{name}' and unregistered {unregistered} tool(s)."
        )
