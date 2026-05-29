import asyncio
import copy
from typing import Any

from loguru import logger

from laffyhand.agent.mcp.client import MCPClient, MCPToolDef
from laffyhand.agent.mcp.config import MCPConfig
from laffyhand.agent.tools.base import BaseTool


class MCPWrappedTool(BaseTool):
    def __init__(self, server_name: str, tool_def: MCPToolDef, client: MCPClient) -> None:
        self._tool_def = tool_def
        self._client = client
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
        logger.info(f"MCP tool call: {self.name}")
        return await self._client.call_tool(self._tool_def.name, params)


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

    async def connect_all(self, configs: dict[str, MCPConfig]) -> None:
        async with asyncio.TaskGroup() as tg:
            for name, cfg in configs.items():
                tg.create_task(self._connect_one(name, cfg))

    async def _connect_one(self, name: str, cfg: MCPConfig) -> None:
        client = MCPClient(name, cfg)
        try:
            await client.connect()
            self._clients[name] = client
            self._status[name] = "connected"
            logger.info(f"MCP '{name}' connected")
        except Exception as e:
            self._status[name] = f"failed: {e}"
            logger.error(f"MCP '{name}' connection failed: {e}")

    async def disconnect(self, name: str) -> None:
        client = self._clients.pop(name, None)
        if client is not None:
            await client.disconnect()
        self._status.pop(name, None)

    async def disconnect_all(self) -> None:
        for name in list(self._clients.keys()):
            await self.disconnect(name)

    async def get_wrapped_tools(self) -> list[BaseTool]:
        tools: list[BaseTool] = []
        for name, client in self._clients.items():
            try:
                defs = await client.list_tools()
                for td in defs:
                    tools.append(MCPWrappedTool(name, td, client))
            except Exception as e:
                logger.warning(f"Failed to list tools for MCP '{name}': {e}")
        return tools

    def get_status(self) -> dict[str, Status]:
        return dict(self._status)
