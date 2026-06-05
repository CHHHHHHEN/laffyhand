from contextlib import AsyncExitStack
from typing import Any, cast

import httpx
from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent

from laffyhand.core.mcp.config import MCPConfig, LocalMCPConfig, RemoteMCPConfig


class MCPToolDef:
    def __init__(
        self, name: str, description: str, input_schema: dict[str, Any]
    ) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema


class MCPClient:
    def __init__(self, name: str, config: MCPConfig) -> None:
        self.name = name
        self.config = config
        self._session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None

    async def connect(self) -> None:
        self._exit_stack = AsyncExitStack()
        try:
            if isinstance(self.config, LocalMCPConfig):
                await self._connect_stdio()
            else:
                await self._connect_remote()
            logger.info(f"MCP client '{self.name}' connected")
        except Exception:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self._session = None
            raise

    async def _connect_stdio(self) -> None:
        assert self._exit_stack is not None
        cfg = cast("LocalMCPConfig", self.config)
        params = StdioServerParameters(
            command=cfg.command[0],
            args=cfg.command[1:],
            env=cfg.env or None,
        )
        read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session

    async def _connect_remote(self) -> None:
        assert self._exit_stack is not None
        cfg = cast("RemoteMCPConfig", self.config)
        transport = cfg.transport
        if transport is None:
            base = cfg.url.split("?")[0].rstrip("/")
            # NOTE: Auto-detection heuristic — checks if URL path ends with "/sse".
            # This is a best-effort guess and may not match all server implementations.
            # Servers with custom paths (e.g. "/mcp/sse", "/v1/stream") may be misidentified.
            # Explicitly set `transport` in MCP_SERVERS config to override.
            transport = "sse" if base.endswith("/sse") else "streamable-http"
            logger.debug(f"Auto-detected MCP transport '{transport}' for '{cfg.url}'")

        if transport == "sse":
            await self._connect_sse(cfg)
        else:
            await self._connect_streamable_http(cfg)

    async def _connect_sse(self, cfg: RemoteMCPConfig) -> None:
        assert self._exit_stack is not None

        def _client_factory(
            headers: dict[str, str] | None = None,
            timeout: httpx.Timeout | None = None,
            auth: httpx.Auth | None = None,
        ) -> httpx.AsyncClient:
            merged: dict[str, Any] = {**(cfg.headers or {})}
            merged.setdefault("Accept", "application/json, text/event-stream")
            if headers:
                merged.update(headers)
            return httpx.AsyncClient(
                headers=merged,
                follow_redirects=True,
                timeout=timeout,
                auth=auth,
            )

        read, write = await self._exit_stack.enter_async_context(
            sse_client(
                cfg.url, httpx_client_factory=_client_factory, timeout=cfg.timeout
            )
        )
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session

    async def _connect_streamable_http(self, cfg: RemoteMCPConfig) -> None:
        assert self._exit_stack is not None
        http_client = await self._exit_stack.enter_async_context(
            httpx.AsyncClient(
                headers=cfg.headers, follow_redirects=True, timeout=cfg.timeout
            )
        )
        read, write, _ = await self._exit_stack.enter_async_context(
            streamable_http_client(cfg.url, http_client=http_client)
        )
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session

    async def disconnect(self) -> None:
        if self._exit_stack is not None:
            try:
                await self._exit_stack.aclose()
            except RuntimeError as e:
                if "different task" in str(e):
                    logger.debug(
                        f"Ignoring task-context error on disconnect for '{self.name}': {e}"
                    )
                else:
                    logger.warning(
                        f"Error closing MCP client '{self.name}': {type(e).__name__}: {e}"
                    )
            except Exception as e:
                logger.warning(
                    f"Error closing MCP client '{self.name}': {type(e).__name__}: {e}"
                )
        self._session = None
        self._exit_stack = None
        logger.info(f"MCP client '{self.name}' disconnected")

    async def list_tools(self) -> list[MCPToolDef]:
        if self._session is None:
            raise RuntimeError(f"MCP client '{self.name}' not connected")
        result = await self._session.list_tools()
        return [
            MCPToolDef(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema or {},
            )
            for tool in result.tools
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        if self._session is None:
            raise RuntimeError(f"MCP client '{self.name}' not connected")
        result: CallToolResult = await self._session.call_tool(tool_name, arguments)
        parts: list[str] = []
        for content in result.content:
            if isinstance(content, TextContent):
                parts.append(content.text)
            else:
                parts.append(str(content))
        text = "\n".join(parts)
        if result.isError:
            text = f"[MCP Error: {self.name}/{tool_name}]\n{text}"
        return text
