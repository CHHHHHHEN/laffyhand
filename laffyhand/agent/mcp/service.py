import asyncio
import copy
from typing import Any

from loguru import logger

from laffyhand.agent.mcp.client import MCPClient, MCPToolDef
from laffyhand.agent.mcp.config import MCPConfig, LocalMCPConfig
from laffyhand.agent.tools.base import BaseTool


class MCPWrappedTool(BaseTool):
    def __init__(self, server_name: str, tool_def: MCPToolDef, service: 'MCPService') -> None:
        self._tool_def = tool_def
        self._server_name = server_name
        self._service = service
        safe_name = tool_def.name.replace("-", "_").replace(".", "_").replace(" ", "_")
        self.name = f"mcp_{server_name}_{safe_name}"
        self.description = tool_def.description

    def _input_schema(self) -> dict:
        schema = dict(self._tool_def.input_schema)
        if "type" not in schema:
            schema["type"] = "object"
        schema.setdefault("additionalProperties", False)
        return _normalize_schema(schema)

    async def run(self, params: dict[str, Any]) -> str:
        client = self._service.get_client(self._server_name)
        if client is None:
            logger.warning(f"MCP server '{self._server_name}' not connected for tool '{self.name}'")
            return f"[MCP Error: server '{self._server_name}' is not connected]"

        try:
            logger.info(f"MCP tool call: {self.name}")
            return await client.call_tool(self._tool_def.name, params)
        except Exception as e:
            logger.warning(f"MCP tool call '{self.name}' failed: {e}, attempting reconnect...")
            ok = await self._service.reconnect(self._server_name)
            if not ok:
                return f"[MCP Error: server '{self._server_name}' reconnection failed]"
            client = self._service.get_client(self._server_name)
            if client is None:
                return f"[MCP Error: server '{self._server_name}' not available after reconnect]"
            logger.info(f"MCP retrying tool call '{self._tool_def.name}' after reconnect")
            return await client.call_tool(self._tool_def.name, params)


def _normalize_schema(schema: dict) -> dict:
    """Normalize JSON schema for OpenAI compatibility (recursive)."""
    result = copy.deepcopy(schema)
    _normalize_schema_node(result)
    return result


def _normalize_schema_node(node: dict) -> None:
    """In-place normalize a single schema node and recurse into children."""
    _strip_null(node)

    for key in ("properties", "patternProperties", "definitions", "$defs"):
        subs = node.get(key)
        if isinstance(subs, dict):
            for sub in subs.values():
                if isinstance(sub, dict):
                    _normalize_schema_node(sub)

    items = node.get("items")
    if isinstance(items, dict):
        _normalize_schema_node(items)
    elif isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                _normalize_schema_node(item)

    additional = node.get("additionalProperties")
    if isinstance(additional, dict):
        _normalize_schema_node(additional)

    for key in ("allOf", "anyOf", "oneOf"):
        subs = node.get(key)
        if isinstance(subs, list):
            for sub in subs:
                if isinstance(sub, dict):
                    _normalize_schema_node(sub)

    not_node = node.get("not")
    if isinstance(not_node, dict):
        _normalize_schema_node(not_node)

    if_schema = node.get("if")
    if isinstance(if_schema, dict):
        _normalize_schema_node(if_schema)
    then_schema = node.get("then")
    if isinstance(then_schema, dict):
        _normalize_schema_node(then_schema)
    else_schema = node.get("else")
    if isinstance(else_schema, dict):
        _normalize_schema_node(else_schema)


def _strip_null(node: dict) -> None:
    """Handle nullable types in a single schema node."""
    type_val = node.get("type")
    if isinstance(type_val, list):
        if "null" in type_val:
            non_null = [t for t in type_val if t != "null"]
            if non_null:
                node["type"] = non_null[0] if len(non_null) == 1 else non_null
                node["nullable"] = True

    for key in ("anyOf", "oneOf"):
        subs = node.get(key)
        if not isinstance(subs, list):
            continue
        null_types = [s for s in subs if isinstance(s, dict) and s.get("type") == "null"]
        if not null_types:
            continue
        non_null = [s for s in subs if isinstance(s, dict) and s.get("type") != "null"]
        if len(non_null) == 1:
            node.clear()
            node.update(non_null[0])
            node["nullable"] = True
        elif non_null:
            node[key] = non_null
            node["nullable"] = True


Status = str


class MCPService:
    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._status: dict[str, Status] = {}
        self._reconnect_cfgs: dict[str, MCPConfig] = {}
        self._reconnect_attempts: dict[str, int] = {}

    def get_client(self, name: str) -> MCPClient | None:
        return self._clients.get(name)

    async def connect_all(self, configs: dict[str, MCPConfig]) -> None:
        # NOTE: 在连接完成前就存储 config，使得首次连接失败的 server
        # 后续仍可通过 reconnect() 重试。如果不需要此行为，可在连接失败后
        # 从 _reconnect_cfgs 中移除对应条目。
        self._reconnect_cfgs.update(configs)
        async with asyncio.TaskGroup() as tg:
            for name, cfg in configs.items():
                tg.create_task(self._connect_one(name, cfg))

    async def connect_server(self, name: str, cfg: MCPConfig) -> list[MCPToolDef]:
        """Connect a single MCP server and return its tools.

        This is the public API for runtime MCP connection.
        Returns a description of discovered tools.
        """
        if name in self._clients:
            raise ValueError(f"MCP server '{name}' is already connected")
        self._reconnect_cfgs[name] = cfg
        client = MCPClient(name, cfg)
        try:
            await client.connect()
        except Exception as e:
            self._status[name] = f"failed: {e}"
            self._reconnect_attempts[name] = 0
            raise
        self._clients[name] = client
        self._status[name] = "connected"
        self._reconnect_attempts[name] = 0
        defs = await client.list_tools()
        logger.info(f"MCP '{name}' connected with {len(defs)} tool(s)")
        return defs

    async def _connect_one(self, name: str, cfg: MCPConfig) -> None:
        cfg_display = str(cfg.command if isinstance(cfg, LocalMCPConfig) else cfg.url)
        logger.debug(f"Connecting MCP '{name}': {cfg_display}")
        client = MCPClient(name, cfg)
        try:
            await client.connect()
            self._clients[name] = client
            self._status[name] = "connected"
            self._reconnect_attempts[name] = 0
            logger.info(f"MCP '{name}' connected")
        except Exception as e:
            self._status[name] = f"failed: {e}"
            self._reconnect_attempts[name] = 0
            logger.error(f"MCP '{name}' connection failed: {e}")

    async def disconnect(self, name: str) -> None:
        client = self._clients.pop(name, None)
        if client is not None:
            await client.disconnect()
        self._status.pop(name, None)
        self._reconnect_cfgs.pop(name, None)
        self._reconnect_attempts.pop(name, None)
        logger.debug(f"MCP '{name}' removed from service")

    async def disconnect_all(self) -> None:
        names = list(self._clients.keys())
        if not names:
            logger.debug("No MCP connections to clean up")
            return
        # Disconnect sequentially to avoid AsyncExitStack task-context errors
        for name in names:
            try:
                await self.disconnect(name)
            except Exception as e:
                logger.warning(f"Error disconnecting MCP '{name}': {e}")
        logger.info(f"Disconnected all MCP clients: {names}")

    async def get_wrapped_tools(self) -> list[BaseTool]:
        tools: list[BaseTool] = []
        for name, client in self._clients.items():
            try:
                defs = await client.list_tools()
                logger.debug(f"Discovered {len(defs)} tool(s) from MCP '{name}'")
                for td in defs:
                    tools.append(MCPWrappedTool(name, td, self))
            except Exception as e:
                logger.warning(f"Failed to list tools for MCP '{name}': {e}")
        logger.info(f"Wrapped {len(tools)} MCP tool(s) total")
        return tools

    async def reconnect(self, name: str) -> bool:
        cfg = self._reconnect_cfgs.get(name)
        if cfg is None:
            logger.warning(f"No config for MCP '{name}', cannot reconnect")
            return False

        max_attempts = 3
        base_delay = 0.5
        current_attempts = self._reconnect_attempts.get(name, 0)

        for attempt in range(1, max_attempts + 1):
            total_attempt = current_attempts + attempt
            try:
                logger.info(f"MCP '{name}' reconnect attempt {attempt}/{max_attempts}...")
                client = MCPClient(name, cfg)
                await client.connect()
                old = self._clients.pop(name, None)
                if old is not None:
                    await old.disconnect()
                self._clients[name] = client
                self._status[name] = "connected"
                self._reconnect_attempts[name] = 0
                logger.info(f"MCP '{name}' reconnected after {total_attempt} total attempt(s)")
                return True
            except Exception as e:
                self._reconnect_attempts[name] = total_attempt
                logger.warning(f"MCP '{name}' reconnect attempt {attempt}/{max_attempts} failed: {e}")
                if attempt < max_attempts:
                    delay = min(base_delay * (2 ** (attempt - 1)), 30.0)
                    logger.debug(f"MCP '{name}' retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)

        self._status[name] = f"disconnected (after {max_attempts} reconnection attempts)"
        logger.error(f"MCP '{name}' failed to reconnect after {max_attempts} attempts")
        return False

    def get_status(self) -> dict[str, Status]:
        return dict(self._status)
