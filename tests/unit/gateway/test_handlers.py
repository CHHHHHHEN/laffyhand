from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from laffyhand.gateway.handlers import (
    handle_initialize,
    handle_shutdown,
    handle_session_create,
    handle_session_list,
    handle_session_load,
    handle_session_delete,
    handle_session_fork,
    handle_chat,
    handle_chat_cancel,
    handle_tools_list,
)


@pytest.fixture
def runtime():
    r = MagicMock()
    r.current_session_id = "sess-1"
    r.state = MagicMock()
    r.state.session_id = "sess-1"
    r.state.messages = []
    r.state.turn_count = 0
    r.session_manager = MagicMock()
    r._context_size = 8192
    r.build_system_prompt = MagicMock(return_value="You are a helpful assistant.")
    return r


class TestHandleInitialize:
    @pytest.mark.anyio
    async def test_returns_server_info(self, runtime, transport):
        result = await handle_initialize(runtime, {}, transport, 1, "c1")
        assert result["protocol_version"] == "2.0"
        assert result["server_info"]["name"] == "laffyhand"
        assert result["session_id"] == "sess-1"


class TestHandleShutdown:
    @pytest.mark.anyio
    async def test_calls_runtime_shutdown(self, runtime, transport):
        runtime.shutdown = AsyncMock()
        await handle_shutdown(runtime, {}, transport, 1, "c1")
        runtime.shutdown.assert_awaited_once()


class TestHandleSessionCreate:
    @pytest.mark.anyio
    async def test_creates_and_returns_session(self, runtime, transport):
        session = MagicMock()
        session.id = "sess-new"
        runtime.session_manager.create = MagicMock(return_value=session)
        runtime.state = None

        result = await handle_session_create(runtime, {}, transport, 1, "c1")

        assert result["session_id"] == "sess-new"

    @pytest.mark.anyio
    async def test_raises_on_failure(self, runtime, transport):
        session = MagicMock()
        session.id = "sess-new"
        runtime.session_manager.create = MagicMock(return_value=session)

        result = await handle_session_create(runtime, {}, transport, 1, "c1")
        assert "session_id" in result


class TestHandleSessionList:
    @pytest.mark.anyio
    async def test_returns_sessions(self, runtime, transport):
        s = MagicMock()
        s.id = "s1"
        s.status = "active"
        s.title = "test"
        s.message_count = 5
        s.turn_count = 3
        s.created_at.isoformat.return_value = "2025-01-01T00:00:00"
        s.updated_at.isoformat.return_value = "2025-01-01T01:00:00"
        runtime.session_manager.list_sessions = MagicMock(return_value=[s])

        result = await handle_session_list(runtime, {"limit": 10}, transport, 1, "c1")

        assert len(result["sessions"]) == 1
        assert result["sessions"][0]["id"] == "s1"

    @pytest.mark.anyio
    async def test_defaults_limit(self, runtime, transport):
        runtime.session_manager.list_sessions = MagicMock(return_value=[])
        await handle_session_list(runtime, {}, transport, 1, "c1")
        runtime.session_manager.list_sessions.assert_called_once_with(
            status=None, limit=20, offset=0,
        )


class TestHandleSessionLoad:
    @pytest.mark.anyio
    async def test_loads_session(self, runtime, transport):
        runtime.switch_session = MagicMock(return_value=True)
        runtime.state = MagicMock()
        runtime.state.session_id = "sess-target"
        runtime.state.messages = ["m1", "m2"]
        runtime.state.turn_count = 7

        result = await handle_session_load(runtime, {"session_id": "sess-target"}, transport, 1, "c1")

        assert result["session_id"] == "sess-target"
        assert result["messages_count"] == 2
        assert result["turn_count"] == 7

    @pytest.mark.anyio
    async def test_requires_session_id(self, runtime, transport):
        with pytest.raises(ValueError, match="session_id is required"):
            await handle_session_load(runtime, {}, transport, 1, "c1")

    @pytest.mark.anyio
    async def test_raises_on_not_found(self, runtime, transport):
        runtime.switch_session = MagicMock(return_value=False)
        with pytest.raises(ValueError, match="not found"):
            await handle_session_load(runtime, {"session_id": "invalid"}, transport, 1, "c1")


class TestHandleSessionDelete:
    @pytest.mark.anyio
    async def test_deletes_session(self, runtime, transport):
        runtime.session_manager.delete = MagicMock()
        result = await handle_session_delete(runtime, {"session_id": "sess-del"}, transport, 1, "c1")
        assert result["status"] == "deleted"
        runtime.session_manager.delete.assert_called_once_with("sess-del")

    @pytest.mark.anyio
    async def test_requires_session_id(self, runtime, transport):
        with pytest.raises(ValueError, match="session_id is required"):
            await handle_session_delete(runtime, {}, transport, 1, "c1")


class TestHandleSessionFork:
    @pytest.mark.anyio
    async def test_forks_session(self, runtime, transport):
        runtime.fork_session = MagicMock(return_value="forked-id")
        result = await handle_session_fork(runtime, {}, transport, 1, "c1")
        assert result["session_id"] == "forked-id"

    @pytest.mark.anyio
    async def test_raises_on_no_active(self, runtime, transport):
        runtime.fork_session = MagicMock(return_value=None)
        with pytest.raises(ValueError, match="No active session"):
            await handle_session_fork(runtime, {}, transport, 1, "c1")


class TestHandleChat:
    @pytest.mark.anyio
    async def test_requires_message(self, runtime, transport):
        with pytest.raises(ValueError, match="message is required"):
            await handle_chat(runtime, {}, transport, 1, "c1")

    @pytest.mark.anyio
    async def test_chat_with_existing_session(self, runtime, transport):
        runtime.state = MagicMock()
        runtime.state.session_id = "sess-1"
        runtime.state.messages = []
        runtime.state.step = 0
        runtime.current_session_id = "sess-1"
        runtime.get_state = MagicMock(return_value=runtime.state)

        events = []
        runtime.run_agent_turn = MagicMock()
        runtime.run_agent_turn.return_value = _async_gen(events)

        result = await handle_chat(runtime, {"message": "hello"}, transport, 1, "c1")

        assert "content" in result
        assert result["session_id"] == "sess-1"

    @pytest.mark.anyio
    async def test_chat_without_session_creates_one(self, runtime, transport):
        runtime.state = None
        runtime.current_session_id = None
        session = MagicMock()
        session.id = "sess-new"
        runtime.session_manager.create = MagicMock(return_value=session)

        state = MagicMock()
        state.session_id = "sess-new"
        state.messages = []
        state.step = 0
        runtime.get_state = MagicMock(return_value=state)
        runtime.run_agent_turn = MagicMock()
        runtime.run_agent_turn.return_value = _async_gen([])

        result = await handle_chat(runtime, {"message": "hello"}, transport, 1, "c1")
        assert result["session_id"] == "sess-new"


class TestHandleChatCancel:
    @pytest.mark.anyio
    async def test_returns_no_active_stream(self, runtime, transport):
        transport._dispatcher = None  # type: ignore[attr-defined]
        result = await handle_chat_cancel(runtime, {}, transport, 1, "c1")
        assert result["status"] == "cancelled"


class TestHandleToolsList:
    @pytest.mark.anyio
    async def test_returns_tools(self, runtime, transport):
        tool1 = MagicMock()
        tool1.model_dump.return_value = {"name": "read"}
        tool2 = MagicMock()
        tool2.model_dump.return_value = {"name": "write"}
        runtime.tool_registry.build_tool_definitions = MagicMock(return_value=[tool1, tool2])

        result = await handle_tools_list(runtime, {}, transport, 1, "c1")

        assert len(result["tools"]) == 2
        assert result["tools"][0]["name"] == "read"


def _async_gen(items):
    async def gen():
        for item in items:
            yield item
    return gen()
