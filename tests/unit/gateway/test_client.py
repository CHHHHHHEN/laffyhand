from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from laffyhand.gateway.client import GatewayClient, RPCError
from laffyhand.gateway.protocol import (
    Response,
    ErrorResponse,
    Notification,
    Error,
)


@pytest.fixture
def transport():
    t = MagicMock()
    t.send = AsyncMock()
    t.recv = AsyncMock()
    t.close = AsyncMock()
    return t


@pytest.fixture
def client(transport):
    return GatewayClient(transport)


class TestRPCError:
    def test_creates_message(self):
        err = RPCError(code=-32601, message="not found")
        assert err.code == -32601
        assert err.message == "not found"
        assert "not found" in str(err)


class TestRequestId:
    def test_increments(self, client):
        assert client._next_id() == 1
        assert client._next_id() == 2
        assert client._next_id() == 3


class TestRequest:
    @pytest.mark.anyio
    async def test_returns_result(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(id=1, result={"ok": True}).json()
        )
        result = await client._request("test", {"a": 1})
        assert result == {"ok": True}
        sent = json.loads(transport.send.call_args[0][0])
        assert sent["method"] == "test"
        assert sent["params"] == {"a": 1}

    @pytest.mark.anyio
    async def test_raises_rpc_error(self, client, transport):
        err = ErrorResponse(id=1, error=Error(code=-32601, message="not found"))
        transport.recv = AsyncMock(return_value=err.json())
        with pytest.raises(RPCError) as exc:
            await client._request("test")
        assert exc.value.code == -32601

    @pytest.mark.anyio
    async def test_skips_unmatched_messages(self, client, transport):
        transport.recv = AsyncMock(
            side_effect=[
                Response(id=999, result={"other": True}).json(),
                Response(id=1, result={"ok": True}).json(),
            ]
        )
        result = await client._request("test")
        assert result == {"ok": True}

    @pytest.mark.anyio
    async def test_raises_on_transport_close(self, client, transport):
        transport.recv = AsyncMock(return_value="")
        with pytest.raises(ConnectionError, match="Transport closed"):
            await client._request("test")

    @pytest.mark.anyio
    async def test_raises_on_timeout(self, client, transport):
        import asyncio

        transport.recv = AsyncMock(side_effect=asyncio.TimeoutError)
        with pytest.raises(asyncio.TimeoutError):
            await client._request("test")

    @pytest.mark.anyio
    async def test_without_params(self, client, transport):
        transport.recv = AsyncMock(return_value=Response(id=1, result="done").json())
        result = await client._request("noop")
        assert result == "done"
        sent = json.loads(transport.send.call_args[0][0])
        assert "params" not in sent or sent["params"] is None


class TestRequestStream:
    @pytest.mark.anyio
    async def test_yields_notifications(self, client, transport):
        transport.recv = AsyncMock(
            side_effect=[
                Notification(
                    method="event", params={"type": "delta", "data": "hello"}
                ).json(),
                Notification(method="event", params={"type": "finish"}).json(),
            ]
        )
        results = []
        async for params in client._request_stream("stream_test"):
            results.append(params)
        assert len(results) == 2
        assert results[0]["data"] == "hello"
        assert results[1]["type"] == "finish"

    @pytest.mark.anyio
    async def test_raises_on_error_response(self, client, transport):
        err = ErrorResponse(id=1, error=Error(code=-32601, message="bad"))
        transport.recv = AsyncMock(return_value=err.json())
        with pytest.raises(RPCError):
            async for _ in client._request_stream("stream_test"):
                pass

    @pytest.mark.anyio
    async def test_skips_null_params(self, client, transport):
        transport.recv = AsyncMock(
            side_effect=[
                Notification(method="event", params=None).json(),
                Notification(method="event", params={"type": "finish"}).json(),
            ]
        )
        results = []
        async for params in client._request_stream("stream_test"):
            results.append(params)
        assert len(results) == 1
        assert results[0]["type"] == "finish"

    @pytest.mark.anyio
    async def test_raises_on_transport_close(self, client, transport):
        transport.recv = AsyncMock(return_value="")
        with pytest.raises(ConnectionError):
            async for _ in client._request_stream("stream_test"):
                pass


class TestInitialize:
    @pytest.mark.anyio
    async def test_returns_server_info(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(
                id=1,
                result={
                    "protocol_version": "2.0",
                    "server_info": {"name": "laffyhand"},
                },
            ).json()
        )
        result = await client.initialize()
        assert result["protocol_version"] == "2.0"


class TestShutdown:
    @pytest.mark.anyio
    async def test_sends_shutdown(self, client, transport):
        transport.recv = AsyncMock(return_value=Response(id=1, result={}).json())
        await client.shutdown()
        sent = json.loads(transport.send.call_args[0][0])
        assert sent["method"] == "shutdown"


class TestSessionCreate:
    @pytest.mark.anyio
    async def test_returns_session_id(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(id=1, result={"session_id": "sess-1"}).json()
        )
        sid = await client.create_session(system_prompt="hello")
        assert sid == "sess-1"

    @pytest.mark.anyio
    async def test_passes_params(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(id=1, result={"session_id": "s-1"}).json()
        )
        await client.create_session(
            system_prompt="sp", title="t", cwd="/tmp", model="m"
        )
        sent = json.loads(transport.send.call_args[0][0])
        assert sent["params"]["system_prompt"] == "sp"
        assert sent["params"]["title"] == "t"
        assert sent["params"]["cwd"] == "/tmp"
        assert sent["params"]["model"] == "m"


class TestSessionList:
    @pytest.mark.anyio
    async def test_returns_sessions(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(
                id=1,
                result={
                    "sessions": [{"id": "s1"}],
                },
            ).json()
        )
        sessions = await client.list_sessions(limit=10)
        assert len(sessions) == 1
        assert sessions[0]["id"] == "s1"

    @pytest.mark.anyio
    async def test_passes_params(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(id=1, result={"sessions": []}).json()
        )
        await client.list_sessions(status="active", limit=5, offset=2)
        sent = json.loads(transport.send.call_args[0][0])
        assert sent["params"]["status"] == "active"
        assert sent["params"]["limit"] == 5
        assert sent["params"]["offset"] == 2


class TestSessionLoad:
    @pytest.mark.anyio
    async def test_returns_session_info(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(
                id=1,
                result={
                    "session_id": "sess-1",
                    "messages_count": 3,
                    "turn_count": 1,
                },
            ).json()
        )
        info = await client.load_session("sess-1")
        assert info["session_id"] == "sess-1"
        assert info["messages_count"] == 3


class TestSessionDelete:
    @pytest.mark.anyio
    async def test_deletes(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(id=1, result={"status": "deleted"}).json()
        )
        await client.delete_session("sess-1")
        sent = json.loads(transport.send.call_args[0][0])
        assert sent["params"]["session_id"] == "sess-1"


class TestSessionFork:
    @pytest.mark.anyio
    async def test_returns_child_id(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(id=1, result={"session_id": "child-1"}).json()
        )
        child_id = await client.fork_session()
        assert child_id == "child-1"


class TestSearchSessions:
    @pytest.mark.anyio
    async def test_returns_matches(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(
                id=1,
                result={
                    "sessions": [{"id": "s1", "title": "Found"}],
                },
            ).json()
        )
        results = await client.search_sessions("test", limit=5)
        assert len(results) == 1
        assert results[0]["title"] == "Found"


class TestSetSessionTitle:
    @pytest.mark.anyio
    async def test_sets_title(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(id=1, result={"status": "ok"}).json()
        )
        await client.set_session_title(title="My Title")
        sent = json.loads(transport.send.call_args[0][0])
        assert sent["params"]["title"] == "My Title"

    @pytest.mark.anyio
    async def test_with_session_id(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(id=1, result={"status": "ok"}).json()
        )
        await client.set_session_title(title="T", session_id="sess-1")
        sent = json.loads(transport.send.call_args[0][0])
        assert sent["params"]["session_id"] == "sess-1"


class TestGenerateSessionTitle:
    @pytest.mark.anyio
    async def test_returns_title(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(id=1, result={"title": "Generated"}).json()
        )
        title = await client.generate_session_title()
        assert title == "Generated"

    @pytest.mark.anyio
    async def test_returns_none(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(id=1, result={"title": None}).json()
        )
        title = await client.generate_session_title()
        assert title is None


class TestArchiveSession:
    @pytest.mark.anyio
    async def test_archives(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(id=1, result={"status": "archived"}).json()
        )
        await client.archive_session(session_id="sess-1")
        sent = json.loads(transport.send.call_args[0][0])
        assert sent["params"]["session_id"] == "sess-1"

    @pytest.mark.anyio
    async def test_archives_empty(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(id=1, result={"status": "archived"}).json()
        )
        await client.archive_session()
        sent = json.loads(transport.send.call_args[0][0])
        assert "session_id" not in sent.get("params", {})


class TestChatStream:
    @pytest.mark.anyio
    async def test_yields_agent_events(self, client, transport):
        transport.recv = AsyncMock(
            side_effect=[
                Notification(
                    method="event",
                    params={"type": "text-delta", "id": "t1", "text": "Hello"},
                ).json(),
                Notification(
                    method="event",
                    params={
                        "type": "finish",
                        "reason": "stop",
                        "usage": {"input_tokens": 10, "output_tokens": 20},
                        "session_usage": {"total_input": 10, "total_output": 20},
                    },
                ).json(),
            ]
        )
        events = []
        async for event in client.chat_stream("hi"):
            events.append(event)
        assert len(events) == 2
        assert events[0].type == "text-delta"
        assert events[0].text == "Hello"
        assert events[1].reason == "stop"
        assert events[1].usage is not None
        assert events[1].usage.input_tokens == 10
        assert events[1].session_usage == {"total_input": 10, "total_output": 20}

    @pytest.mark.anyio
    async def test_handles_no_usage(self, client, transport):
        transport.recv = AsyncMock(
            side_effect=[
                Notification(
                    method="event", params={"type": "finish", "reason": "stop"}
                ).json(),
            ]
        )
        events = []
        async for event in client.chat_stream("hi"):
            events.append(event)
        assert events[0].usage is None
        assert events[0].session_usage is None


class TestCancelChat:
    @pytest.mark.anyio
    async def test_cancels(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(id=1, result={"status": "cancelled"}).json()
        )
        await client.cancel_chat()
        sent = json.loads(transport.send.call_args[0][0])
        assert sent["method"] == "chat/cancel"


class TestListActiveSubagents:
    @pytest.mark.anyio
    async def test_returns_subagents(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(
                id=1,
                result={
                    "subagents": [{"task_id": "t1", "status": "running"}],
                },
            ).json()
        )
        agents = await client.list_active_subagents()
        assert len(agents) == 1
        assert agents[0]["task_id"] == "t1"


class TestGetUsage:
    @pytest.mark.anyio
    async def test_returns_usage(self, client, transport):
        transport.recv = AsyncMock(
            return_value=Response(
                id=1,
                result={
                    "usage": {"total_input": 100, "total_output": 50},
                },
            ).json()
        )
        result = await client.get_usage()
        assert result["usage"]["total_input"] == 100
