from typing import Any

from loguru import logger

from laffyhand.agent.mcp.client import MCPClient, MCPToolDef
from laffyhand.agent.mcp.config import MCPConfig
from laffyhand.agent.tools.base import BaseTool


class MCPWrappedTool(BaseTool):
    def __init__(self, server_name: str, tool_def: MCPToolDef, client: MCPClient) -> None:
        self._server_name = server_name
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
    """Normalize JSON schema for OpenAI compatibility."""
    result = dict(schema)
    props = result.get("properties", {})
    for key, prop in props.items():
        if isinstance(prop, dict):
            prop_types = prop.get("type")
            if isinstance(prop_types, list):
                if "null" in prop_types:
                    non_null = [t for t in prop_types if t != "null"]
                    prop["type"] = non_null[0] if len(non_null) == 1 else non_null
                    prop["nullable"] = True
            any_of = prop.get("anyOf")
            if isinstance(any_of, list):
                null_types = [s for s in any_of if isinstance(s, dict) and s.get("type") == "null"]
                if null_types:
                    non_null = [s for s in any_of if isinstance(s, dict) and s.get("type") != "null"]
                    if len(non_null) == 1:
                        prop.clear()
                        prop.update(non_null[0])
                        prop["nullable"] = True
                    elif non_null:
                        prop["anyOf"] = non_null
                        prop["nullable"] = True
            one_of = prop.get("oneOf")
            if isinstance(one_of, list):
                null_types = [s for s in one_of if isinstance(s, dict) and s.get("type") == "null"]
                if null_types:
                    non_null = [s for s in one_of if isinstance(s, dict) and s.get("type") != "null"]
                    if len(non_null) == 1:
                        prop.clear()
                        prop.update(non_null[0])
                        prop["nullable"] = True
                    elif non_null:
                        prop["oneOf"] = non_null
                        prop["nullable"] = True
    return result


Status = str


class MCPService:
    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._status: dict[str, Status] = {}

    async def connect_all(self, configs: dict[str, MCPConfig]) -> None:
        for name, cfg in configs.items():
            await self._connect_one(name, cfg)

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
