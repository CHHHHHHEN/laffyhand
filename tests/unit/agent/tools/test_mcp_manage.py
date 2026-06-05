from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from laffyhand.core.tools.mcp_manage import (
    MCPConnectTool,
    MCPDisconnectTool,
    MCPListTool,
)


@pytest.fixture
def mcp_service():
    svc = MagicMock()
    svc.disconnect = AsyncMock()
    return svc


@pytest.fixture
def tool_registry():
    return MagicMock()


class TestMCPListTool:
    @pytest.fixture
    def tool(self, mcp_service):
        return MCPListTool(mcp_service)

    @pytest.mark.anyio
    async def test_no_servers(self, tool, mcp_service):
        mcp_service.get_status.return_value = {}
        result = await tool.run({})
        assert result == "No MCP servers configured or connected."

    @pytest.mark.anyio
    async def test_with_servers(self, tool, mcp_service):
        mcp_service.get_status.return_value = {
            "server-a": "connected",
            "server-b": "error: timeout",
        }
        result = await tool.run({})
        assert "MCP Servers" in result
        assert "server-a" in result
        assert "connected" in result
        assert "server-b" in result
        assert "error: timeout" in result


class TestMCPConnectTool:
    @pytest.fixture
    def tool(self, mcp_service, tool_registry):
        return MCPConnectTool(mcp_service, tool_registry)

    @pytest.fixture(autouse=True)
    def _not_connected(self, mcp_service):
        mcp_service.get_client.return_value = None

    @pytest.mark.anyio
    async def test_invalid_url_scheme_http(self, tool):
        result = await tool.run({"name": "s", "url": "http://example.com/mcp"})
        assert "https://" in result

    @pytest.mark.anyio
    async def test_localhost_hostname(self, tool):
        result = await tool.run({"name": "s", "url": "https://localhost:9090/mcp"})
        assert "localhost" in result

    @pytest.mark.anyio
    async def test_loopback_ip(self, tool):
        result = await tool.run({"name": "s", "url": "https://127.0.0.1:9090/mcp"})
        assert "not allowed" in result

    @pytest.mark.anyio
    async def test_private_ip(self, tool):
        result = await tool.run({"name": "s", "url": "https://192.168.1.1/mcp"})
        assert "not allowed" in result

    @pytest.mark.anyio
    async def test_disallowed_command(self, tool):
        result = await tool.run({"name": "s", "command": ["curl", "https://x.com"]})
        assert "not allowed" in result
        assert "curl" in result

    @pytest.mark.anyio
    async def test_empty_command_treated_as_not_provided(self, tool):
        result = await tool.run({"name": "s", "command": []})
        assert "must be provided" in result

    @pytest.mark.anyio
    async def test_python_inline_code(self, tool):
        result = await tool.run({"name": "s", "command": ["python", "-c", "print(1)"]})
        assert "-c" in result
        assert "not allowed" in result

    @pytest.mark.anyio
    async def test_python3_inline_code(self, tool):
        result = await tool.run({"name": "s", "command": ["python3", "-c", "print(1)"]})
        assert "-c" in result
        assert "not allowed" in result

    @pytest.mark.anyio
    async def test_node_inline_code(self, tool):
        result = await tool.run(
            {"name": "s", "command": ["node", "-e", "console.log(1)"]}
        )
        assert "-e" in result
        assert "not allowed" in result

    @pytest.mark.anyio
    async def test_deno_inline_code(self, tool):
        result = await tool.run(
            {"name": "s", "command": ["deno", "eval", "console.log(1)"]}
        )
        assert "eval" in result
        assert "not allowed" in result

    @pytest.mark.anyio
    async def test_shell_metacharacters(self, tool):
        result = await tool.run({"name": "s", "command": ["npx", "package; rm -rf /"]})
        assert "metacharacters" in result

    @pytest.mark.anyio
    async def test_shell_backtick(self, tool):
        result = await tool.run({"name": "s", "command": ["npx", "`whoami`"]})
        assert "metacharacters" in result

    @pytest.mark.anyio
    async def test_neither_url_nor_command(self, tool):
        result = await tool.run({"name": "s"})
        assert "must be provided" in result

    @pytest.mark.anyio
    async def test_already_connected(self, tool, mcp_service):
        mcp_service.get_client.return_value = MagicMock()
        result = await tool.run({"name": "s", "command": ["npx", "something"]})
        assert "already connected" in result

    @pytest.mark.anyio
    async def test_successful_connect_local(self, tool, mcp_service, tool_registry):
        tool_def = MagicMock()
        tool_def.name = "my_tool"
        mcp_service.connect_server = AsyncMock(return_value=[tool_def])

        result = await tool.run({"name": "test", "command": ["npx", "something"]})

        mcp_service.connect_server.assert_awaited_once()
        tool_registry.register_tool.assert_called_once()
        assert "Connected" in result
        assert "test" in result
        assert "my_tool" in result

    @pytest.mark.anyio
    async def test_successful_connect_remote(self, tool, mcp_service, tool_registry):
        tool_def = MagicMock()
        tool_def.name = "remote_tool"
        mcp_service.connect_server = AsyncMock(return_value=[tool_def])

        result = await tool.run(
            {
                "name": "remote",
                "url": "https://example.com/mcp",
                "transport": "sse",
                "headers": {"Authorization": "Bearer x"},
            }
        )

        mcp_service.connect_server.assert_awaited_once()
        tool_registry.register_tool.assert_called_once()
        assert "Connected" in result
        assert "remote" in result

    @pytest.mark.anyio
    async def test_connect_failure(self, tool, mcp_service):
        mcp_service.connect_server = AsyncMock(side_effect=Exception("boom"))
        result = await tool.run({"name": "s", "command": ["npx", "something"]})
        assert "Failed to connect" in result


class TestMCPDisconnectTool:
    @pytest.fixture
    def tool(self, mcp_service, tool_registry):
        return MCPDisconnectTool(mcp_service, tool_registry)

    @pytest.mark.anyio
    async def test_not_connected(self, tool, mcp_service):
        mcp_service.get_client.return_value = None
        result = await tool.run({"name": "test"})
        assert "not connected" in result
        mcp_service.disconnect.assert_not_called()

    @pytest.mark.anyio
    async def test_disconnect_no_tools(self, tool, mcp_service, tool_registry):
        mcp_service.get_client.return_value = MagicMock()
        tool_registry.unregister_by_prefix.return_value = 0

        result = await tool.run({"name": "test"})

        mcp_service.disconnect.assert_awaited_once_with("test")
        tool_registry.unregister_by_prefix.assert_called_once_with("mcp_test_")
        assert "0 tool(s)" in result

    @pytest.mark.anyio
    async def test_disconnect_with_tools(self, tool, mcp_service, tool_registry):
        mcp_service.get_client.return_value = MagicMock()
        tool_registry.unregister_by_prefix.return_value = 2

        result = await tool.run({"name": "test"})

        tool_registry.unregister_by_prefix.assert_called_once_with("mcp_test_")
        mcp_service.disconnect.assert_awaited_once_with("test")
        assert "2 tool(s)" in result

    @pytest.mark.anyio
    async def test_disconnect_multiple_servers(self, tool, mcp_service, tool_registry):
        mcp_service.get_client.return_value = MagicMock()
        tool_registry.unregister_by_prefix.return_value = 1

        result = await tool.run({"name": "foo"})

        tool_registry.unregister_by_prefix.assert_called_once_with("mcp_foo_")
        mcp_service.disconnect.assert_awaited_once_with("foo")
        assert "1 tool(s)" in result
