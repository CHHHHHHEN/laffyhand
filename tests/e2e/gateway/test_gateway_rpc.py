from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from laffyhand.gateway.server import GatewayServer
from laffyhand.gateway.transport import InProcessTransport
from laffyhand.gateway.protocol import Request
from laffyhand.gateway.dispatcher import Dispatcher
from laffyhand.gateway.handlers import register_all_handlers


@pytest.fixture
def runtime():
    r = MagicMock()
    r.current_session_id = None
    r.state = None
    r.context_size = 128000
    r.tool_registry.build_tool_definitions = MagicMock(return_value=[])
    r.tool_registry.build_tool_prompt = MagicMock(return_value="")
    r.skill_registry.all = MagicMock(return_value=[])
    r.session_manager = MagicMock()
    r.session_manager.create = MagicMock(return_value=MagicMock(id="sess-1"))
    r.session_manager.list_sessions = MagicMock(return_value=[])
    return r


@pytest.fixture
def transport_pair():
    return InProcessTransport.create_pair()


async def _run_gateway(gateway: GatewayServer) -> None:
    import asyncio
    try:
        await asyncio.wait_for(gateway.serve(), timeout=5)
    except asyncio.TimeoutError:
        pass


async def _shutdown_gateway(client_t: InProcessTransport) -> None:
    req = Request(id=99, method="shutdown", params={})
    await client_t.send(req.json())


@pytest.mark.anyio
async def test_initialize(transport_pair):
    server_t, client_t = transport_pair
    runtime = MagicMock()
    runtime.current_session_id = "sess-1"
    gateway = GatewayServer(runtime, server_t)

    import asyncio
    task = asyncio.create_task(_run_gateway(gateway))
    await asyncio.sleep(0.05)

    req = Request(id=1, method="initialize", params={})
    await client_t.send(req.json())
    raw = await asyncio.wait_for(client_t.recv(), timeout=2)
    resp = json.loads(raw)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert resp["result"]["server_info"]["name"] == "laffyhand"

    await _shutdown_gateway(client_t)
    await task


@pytest.mark.anyio
async def test_tools_list_empty(transport_pair):
    server_t, client_t = transport_pair
    runtime = MagicMock()
    runtime.tool_registry.build_tool_definitions = MagicMock(return_value=[])
    gateway = GatewayServer(runtime, server_t)

    import asyncio
    task = asyncio.create_task(_run_gateway(gateway))
    await asyncio.sleep(0.05)

    req = Request(id=1, method="tools/list", params={})
    await client_t.send(req.json())
    raw = await asyncio.wait_for(client_t.recv(), timeout=2)
    resp = json.loads(raw)
    assert resp["id"] == 1
    assert resp["result"]["tools"] == []

    await _shutdown_gateway(client_t)
    await task


@pytest.mark.anyio
async def test_method_not_found(transport_pair):
    server_t, client_t = transport_pair
    runtime = MagicMock()
    gateway = GatewayServer(runtime, server_t)

    import asyncio
    task = asyncio.create_task(_run_gateway(gateway))
    await asyncio.sleep(0.05)

    req = Request(id=1, method="nonexistent", params={})
    await client_t.send(req.json())
    raw = await asyncio.wait_for(client_t.recv(), timeout=2)
    resp = json.loads(raw)
    assert resp["id"] == 1
    assert "error" in resp
    assert resp["error"]["code"] == -32601

    await _shutdown_gateway(client_t)
    await task


@pytest.mark.anyio
async def test_invalid_json(transport_pair):
    server_t, client_t = transport_pair
    runtime = MagicMock()
    gateway = GatewayServer(runtime, server_t)

    import asyncio
    task = asyncio.create_task(_run_gateway(gateway))
    await asyncio.sleep(0.05)

    await client_t.send("not json")
    raw = await asyncio.wait_for(client_t.recv(), timeout=2)
    resp = json.loads(raw)
    assert "error" in resp

    await _shutdown_gateway(client_t)
    await task


@pytest.mark.anyio
async def test_session_lifecycle(runtime, transport_pair):
    """Session create, list, load end-to-end via gateway."""
    server_t, client_t = transport_pair
    gateway = GatewayServer(runtime, server_t)

    import asyncio
    task = asyncio.create_task(_run_gateway(gateway))
    await asyncio.sleep(0.05)

    # No active session initially — create one via session/create
    session = MagicMock()
    session.id = "sess-new"
    runtime.session_manager.create.return_value = session
    runtime.state = MagicMock()
    runtime.state.session_id = "sess-new"
    runtime.build_system_prompt = MagicMock(return_value="You are a helpful assistant.")

    req = Request(id=1, method="session/create", params={})
    await client_t.send(req.json())
    raw = await asyncio.wait_for(client_t.recv(), timeout=2)
    resp = json.loads(raw)
    assert resp["id"] == 1
    assert resp["result"]["session_id"] == "sess-new"

    # List sessions
    runtime.session_manager.list_sessions.return_value = [session]

    req = Request(id=2, method="session/list", params={})
    await client_t.send(req.json())
    raw = await asyncio.wait_for(client_t.recv(), timeout=2)
    resp = json.loads(raw)
    assert resp["id"] == 2

    await _shutdown_gateway(client_t)
    await task


@pytest.mark.anyio
async def test_rpc_handler_error_logging(transport_pair):
    """Ensure internal errors don't leak details to the client."""
    server_t, client_t = transport_pair
    runtime = MagicMock()

    # Create a dispatcher with a handler that raises
    dispatcher = Dispatcher(runtime=runtime)
    register_all_handlers(dispatcher)

    gateway = GatewayServer(runtime, server_t)
    gateway.dispatcher = dispatcher

    import asyncio
    task = asyncio.create_task(_run_gateway(gateway))
    await asyncio.sleep(0.05)

    runtime.switch_session = MagicMock(side_effect=ValueError("internal db failure"))

    req = Request(id=1, method="session/load", params={"session_id": "bad"})
    await client_t.send(req.json())
    raw = await asyncio.wait_for(client_t.recv(), timeout=2)
    resp = json.loads(raw)
    assert resp["id"] == 1
    assert "error" in resp
    assert resp["error"]["code"] == -32603
    assert "internal db failure" not in str(resp)  # should not leak details

    await _shutdown_gateway(client_t)
    await task
