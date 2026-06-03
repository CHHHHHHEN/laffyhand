from __future__ import annotations

import json
from unittest.mock import MagicMock, AsyncMock

import pytest

from laffyhand.gateway.server import GatewayServer
from laffyhand.gateway.transport import InProcessTransport
from laffyhand.gateway.protocol import Request
from laffyhand.gateway.dispatcher import Dispatcher
from laffyhand.gateway.handlers import register_all_handlers


@pytest.fixture
def runtime():
    r = MagicMock()
    r._states = {}
    r.get_state = MagicMock(side_effect=lambda sid: r._states.get(sid))
    r.context_size = 128000
    r.tool_registry.build_tool_definitions = AsyncMock(return_value=[])
    r.tool_registry.build_tool_prompt = MagicMock(return_value="")
    r.skill_registry.all = MagicMock(return_value=[])
    r.session_manager = MagicMock()
    r.session_manager.create = MagicMock(return_value=MagicMock(id="sess-1"))
    r.session_manager.list_sessions = MagicMock(return_value=[])
    r._generate_title = AsyncMock()
    r._schedule_title_generation = MagicMock()
    r.get_session_lock = MagicMock(return_value=MagicMock())
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


async def _mock_run_agent_turn(**kwargs):
    from laffyhand.agent.schemas import TextDelta, StepFinish
    from laffyhand.agent.llm.specs.models import Usage

    yield TextDelta(id="text-1", text="Hello from LLM")
    yield StepFinish(
        index=1, reason="stop", usage=Usage(input_tokens=10, output_tokens=5)
    )


@pytest.mark.anyio
async def test_initialize(transport_pair):
    server_t, client_t = transport_pair
    runtime = MagicMock()
    runtime._states = {}
    runtime.get_state = MagicMock(side_effect=lambda sid: runtime._states.get(sid))
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
    runtime.tool_registry = MagicMock()
    runtime.tool_registry.build_tool_definitions = AsyncMock(return_value=[])
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
    runtime.build_system_prompt = AsyncMock(return_value="You are a helpful assistant.")

    req = Request(id=1, method="session/create", params={})
    await client_t.send(req.json())
    raw = await asyncio.wait_for(client_t.recv(), timeout=2)
    resp = json.loads(raw)
    assert resp["id"] == 1
    session_id = resp["result"]["session_id"]
    assert session_id is not None and isinstance(session_id, str)

    # Build a mock session for listing
    list_session = MagicMock()
    list_session.id = session_id
    list_session.status = "active"
    list_session.title = ""
    list_session.message_count = 0
    list_session.turn_count = 0
    list_session.input_tokens = 0
    list_session.output_tokens = 0
    list_session.created_at.isoformat.return_value = "2025-01-01T00:00:00"
    list_session.updated_at.isoformat.return_value = "2025-01-01T01:00:00"
    runtime.session_manager.list_sessions.return_value = [list_session]

    req = Request(id=2, method="session/list", params={})
    await client_t.send(req.json())
    raw = await asyncio.wait_for(client_t.recv(), timeout=2)
    resp = json.loads(raw)
    assert resp["id"] == 2

    await _shutdown_gateway(client_t)
    await task


@pytest.mark.anyio
async def test_chat_stream_via_gateway(transport_pair):
    """End-to-end chat_stream: sends message, receives streamed notifications, then finish."""
    server_t, client_t = transport_pair
    runtime = MagicMock()
    runtime._states = {}
    runtime.get_state = MagicMock(side_effect=lambda sid: runtime._states.get(sid))
    runtime.context_size = 128000
    runtime.tool_registry.build_tool_definitions = MagicMock(return_value=[])
    runtime.tool_registry.build_tool_prompt = MagicMock(return_value="")
    runtime.skill_registry.all = MagicMock(return_value=[])
    runtime.build_system_prompt = AsyncMock(return_value="You are helpful.")
    runtime.session_manager = MagicMock()
    runtime.session_manager.create = MagicMock(return_value=MagicMock(id="sess-stream"))
    runtime.run_agent_turn = _mock_run_agent_turn
    runtime._generate_title = AsyncMock()
    runtime._schedule_title_generation = MagicMock()
    runtime.get_session_lock = MagicMock(return_value=MagicMock())
    runtime.subagent_manager = None

    import asyncio

    gateway = GatewayServer(runtime, server_t)
    task = asyncio.create_task(_run_gateway(gateway))
    await asyncio.sleep(0.05)

    # First create a session so there's a state
    usage_mock = MagicMock()
    usage_mock.model_dump.return_value = {"total_input": 10, "total_output": 5}
    state = MagicMock()
    state.session_id = "sess-stream"
    state.messages = []
    state.step = 0
    state.pending_steer = None
    state.usage = usage_mock
    runtime._states["sess-stream"] = state

    req = Request(id=1, method="chat/stream", params={"message": "hello", "session_id": "sess-stream"})
    await client_t.send(req.json())

    notifications = []
    while True:
        raw = await asyncio.wait_for(client_t.recv(), timeout=5)
        from laffyhand.gateway.protocol import from_json, Notification

        msg = from_json(raw)
        if isinstance(msg, Notification) and msg.method == "event":
            notifications.append(msg.params)
            if msg.params and msg.params.get("type") == "finish":
                break

    assert len(notifications) >= 2
    text_notif = notifications[0]
    assert text_notif["type"] == "text-delta"
    assert "Hello" in text_notif["text"]
    finish_notif = notifications[-1]
    assert finish_notif["type"] == "finish"
    assert finish_notif["reason"] == "stop"
    assert finish_notif["session_id"] == "sess-stream"
    assert finish_notif["session_usage"] == {"total_input": 10, "total_output": 5}

    await _shutdown_gateway(client_t)
    await task


@pytest.mark.anyio
async def test_session_set_title_via_gateway(transport_pair):
    server_t, client_t = transport_pair
    runtime = MagicMock()
    runtime.session_manager = MagicMock()
    gateway = GatewayServer(runtime, server_t)

    import asyncio

    task = asyncio.create_task(_run_gateway(gateway))
    await asyncio.sleep(0.05)

    req = Request(id=1, method="session/set_title", params={"title": "Custom Title", "session_id": "sess-1"})
    await client_t.send(req.json())
    raw = await asyncio.wait_for(client_t.recv(), timeout=2)
    resp = json.loads(raw)
    assert resp["result"]["title"] == "Custom Title"
    runtime.session_manager.set_title.assert_called_once_with("sess-1", "Custom Title")

    await _shutdown_gateway(client_t)
    await task


@pytest.mark.anyio
async def test_usage_get_via_gateway(transport_pair):
    server_t, client_t = transport_pair
    runtime = MagicMock()

    usage_mock = MagicMock()
    usage_mock.total_input = 100
    usage_mock.total_output = 50
    usage_mock.total_reasoning = 10
    usage_mock.total_cache_read = 5
    usage_mock.context_size = 8192
    state_mock = MagicMock()
    state_mock.usage = usage_mock
    runtime._states = {"sess-1": state_mock}
    runtime.get_state = MagicMock(side_effect=lambda sid: runtime._states.get(sid))

    gateway = GatewayServer(runtime, server_t)

    import asyncio

    task = asyncio.create_task(_run_gateway(gateway))
    await asyncio.sleep(0.05)

    req = Request(id=1, method="usage/get", params={"session_id": "sess-1"})
    await client_t.send(req.json())
    raw = await asyncio.wait_for(client_t.recv(), timeout=2)
    resp = json.loads(raw)
    assert resp["result"]["total_input"] == 100
    assert resp["result"]["total_output"] == 50
    assert resp["result"]["total_reasoning"] == 10
    assert resp["result"]["context_size"] == 8192

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

    runtime.load_session_state = MagicMock(side_effect=ValueError("internal db failure"))

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
