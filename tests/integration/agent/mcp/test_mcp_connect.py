import sys
import tempfile
from pathlib import Path

import pytest

from laffyhand.core.mcp.config import LocalMCPConfig
from laffyhand.core.mcp.service import MCPService


pytestmark = pytest.mark.anyio


MCP_SERVER_SCRIPT = r"""
import json, sys

sys.stdin.reconfigure(line_buffering=True)
sys.stdout.reconfigure(line_buffering=True)

def send(msg):
    line = json.dumps(msg)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()

def recv():
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)

req = recv()
send({
    "jsonrpc": "2.0", "id": req["id"],
    "result": {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "test-server", "version": "1.0.0"}
    }
})

notif = recv()

while True:
    req = recv()
    if req is None:
        break
    method = req.get("method", "")
    req_id = req.get("id")

    if method == "tools/list":
        send({
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "tools": [
                    {"name": "echo", "description": "Echo back input",
                     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
                    {"name": "add", "description": "Add two numbers",
                     "inputSchema": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]}},
                ]
            }
        })
    elif method == "tools/call":
        params = req.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {})
        if name == "echo":
            result_text = f"echo: {args.get('text', '')}"
        elif name == "add":
            result_text = str(args.get("a", 0) + args.get("b", 0))
        else:
            result_text = f"unknown: {name}"
        send({
            "jsonrpc": "2.0", "id": req_id,
            "result": {"content": [{"type": "text", "text": result_text}], "meta": {}}
        })
    else:
        send({
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"unknown method: {method}"}
        })
"""


@pytest.fixture(scope="module")
def server_file():
    sf = Path(tempfile.mktemp(suffix=".py"))
    sf.write_text(MCP_SERVER_SCRIPT, encoding="utf-8")
    yield sf
    sf.unlink(missing_ok=True)


@pytest.fixture
async def mcp_service(server_file):
    service = MCPService()
    cfg = LocalMCPConfig(
        command=[sys.executable, str(server_file)],
        env={"PYTHONUNBUFFERED": "1"},
    )
    await service.connect_all({"test": cfg})
    yield service
    await service.disconnect_all()


class TestMCPIntegration:
    async def test_connected_status(self, mcp_service):
        status = mcp_service.get_status()
        assert "test" in status
        assert status["test"] == "connected"

    async def test_discovers_tools(self, mcp_service):
        tools = await mcp_service.get_wrapped_tools()
        names = [t.name for t in tools]
        assert "mcp_test_echo" in names
        assert "mcp_test_add" in names

    async def test_echo_tool_execution(self, mcp_service):
        tools = await mcp_service.get_wrapped_tools()
        echo_tool = [t for t in tools if t.name == "mcp_test_echo"][0]
        result = await echo_tool.run({"text": "hello world"})
        assert "echo: hello world" in result

    async def test_add_tool_execution(self, mcp_service):
        tools = await mcp_service.get_wrapped_tools()
        add_tool = [t for t in tools if t.name == "mcp_test_add"][0]
        result = await add_tool.run({"a": 3, "b": 4})
        assert result.strip() == "7"

    async def test_tool_input_schema(self, mcp_service):
        tools = await mcp_service.get_wrapped_tools()
        echo_tool = [t for t in tools if t.name == "mcp_test_echo"][0]
        schema = echo_tool._input_schema()
        assert "text" in schema.get("properties", {})
