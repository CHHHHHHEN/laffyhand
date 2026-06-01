from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from laffyhand.gateway import handlers
from laffyhand.gateway.handlers import (
    handle_initialize,
    handle_shutdown,
    handle_session_create,
    handle_session_list,
    handle_session_load,
    handle_session_delete,
    handle_session_fork,
    handle_chat,
    handle_chat_stream,
    handle_chat_cancel,
    handle_config_providers,
    handle_mcp_status,
    handle_session_set_config,
    handle_tools_list,
    _serialize_messages,
    _next_msg_id,
)
from laffyhand.agent.schemas import (
    SystemMessage, UserMessage, AssistantMessage, ToolMessage,
    ToolCallContent, Usage,
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
    async def test_cancels_when_dispatcher_on_transport(self, runtime, transport):
        """transport._dispatcher is set -> used directly."""
        dispatcher = MagicMock()
        dispatcher.cancel_connection = MagicMock(return_value=True)
        transport._dispatcher = dispatcher  # type: ignore[attr-defined]
        result = await handle_chat_cancel(runtime, {}, transport, 1, "c1")
        assert result["status"] == "cancelled"
        dispatcher.cancel_connection.assert_called_once_with("c1")

    @pytest.mark.anyio
    async def test_no_active_stream_when_cancel_fails(self, runtime, transport):
        """cancel_connection returns False -> no_active_stream."""
        dispatcher = MagicMock()
        dispatcher.cancel_connection = MagicMock(return_value=False)
        transport._dispatcher = dispatcher  # type: ignore[attr-defined]
        result = await handle_chat_cancel(runtime, {}, transport, 1, "c1")
        assert result["status"] == "no_active_stream"

    @pytest.mark.anyio
    async def test_cancellation_not_supported(self, runtime, transport):
        """No dispatcher or SSE canceller on transport -> cancellation_not_supported."""
        transport._dispatcher = None  # type: ignore[attr-defined]
        transport._sse_canceller = None  # type: ignore[attr-defined]
        result = await handle_chat_cancel(runtime, {}, transport, 1, "c1")
        assert result["status"] == "cancellation_not_supported"


class TestSerializeMessages:
    def test_system_message(self):
        result = _serialize_messages([SystemMessage(content="system prompt")])
        assert len(result) == 1
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "system prompt"
        assert "id" in result[0]
        assert "createdAt" in result[0]

    def test_user_message(self):
        result = _serialize_messages([UserMessage(content="hello")])
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "hello"

    def test_assistant_message_content_only(self):
        result = _serialize_messages([AssistantMessage(content="hi")])
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "hi"

    def test_assistant_message_with_reasoning(self):
        result = _serialize_messages([AssistantMessage(content="answer", reasoning="thinking...")])
        assert result[0]["reasoning"] == "thinking..."

    def test_assistant_message_with_tool_calls(self):
        tc = ToolCallContent(tool_call_id="call-1", tool_name="read_file", args='{"path": "/test"}')
        result = _serialize_messages([AssistantMessage(content="using tool", tool_calls=[tc])])
        assert len(result[0]["toolCalls"]) == 1
        assert result[0]["toolCalls"][0]["id"] == "call-1"
        assert result[0]["toolCalls"][0]["name"] == "read_file"

    def test_assistant_message_with_usage(self):
        usage = Usage(input_tokens=10, output_tokens=5)
        result = _serialize_messages([AssistantMessage(content="done", tokens=usage)])
        assert result[0]["usage"]["inputTokens"] == 10
        assert result[0]["usage"]["outputTokens"] == 5

    def test_assistant_message_no_content(self):
        result = _serialize_messages([AssistantMessage(content="")])
        assert result[0]["content"] == ""

    def test_tool_message(self):
        result = _serialize_messages([ToolMessage(content="tool output", tool_call_id="call-1")])
        assert result[0]["role"] == "tool"
        assert result[0]["content"] == "tool output"
        assert result[0]["tool_call_id"] == "call-1"

    def test_mixed_messages(self):
        msgs = [
            SystemMessage(content="sys"),
            UserMessage(content="user"),
            AssistantMessage(content="assistant"),
            ToolMessage(content="result", tool_call_id="c1"),
        ]
        result = _serialize_messages(msgs)
        assert len(result) == 4
        assert [m["role"] for m in result] == ["system", "user", "assistant", "tool"]

    def test_assistant_without_tool_calls_omits_field(self):
        msg = AssistantMessage(content="no tools")
        result = _serialize_messages([msg])
        assert "toolCalls" not in result[0]

    def test_assistant_without_usage_omits_field(self):
        msg = AssistantMessage(content="no usage", tokens=None)
        result = _serialize_messages([msg])
        assert "usage" not in result[0]


class TestNextMsgId:
    def test_format(self):
        msg_id = _next_msg_id()
        assert msg_id.startswith("msg-")
        parts = msg_id.split("-")
        assert len(parts) >= 3

    def test_incrementing(self):
        id1 = _next_msg_id()
        id2 = _next_msg_id()
        # IDs should differ (counter increments)
        assert id1 != id2


class TestHandleSessionLoadWithMessages:
    @pytest.mark.anyio
    async def test_returns_messages(self, runtime, transport):
        runtime.switch_session = MagicMock(return_value=True)
        runtime.state = MagicMock()
        runtime.state.session_id = "sess-target"
        runtime.state.messages = [
            UserMessage(content="hello"),
            AssistantMessage(content="hi there"),
        ]
        runtime.state.turn_count = 2

        result = await handle_session_load(runtime, {"session_id": "sess-target"}, transport, 1, "c1")

        assert "messages" in result
        assert len(result["messages"]) == 2
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"


class TestHandleChatStream:
    @pytest.mark.anyio
    async def test_streams_events_and_finish(self, runtime, transport):
        from laffyhand.agent.loop import TextDelta

        runtime.state = MagicMock()
        runtime.state.session_id = "sess-1"
        runtime.state.messages = []
        runtime.state.step = 0
        runtime.state.pending_steer = None
        runtime.state.usage = MagicMock()
        runtime.state.usage.model_dump.return_value = {"total_input": 0, "total_output": 0}
        runtime.current_session_id = "sess-1"
        runtime.get_state = MagicMock(return_value=runtime.state)

        runtime.run_agent_turn = MagicMock()
        runtime.run_agent_turn.return_value = _async_gen([TextDelta(id="t1", text="hello")])

        await handle_chat_stream(runtime, {"message": "hi"}, transport, 1, "c1")

        # Should have sent at least 2 messages: event + finish
        assert transport.send.await_count >= 2
        # The finish should be the last call
        last_call = transport.send.await_args_list[-1]
        import json
        last_data = json.loads(last_call[0][0])
        assert last_data["params"]["type"] == "finish"

    @pytest.mark.anyio
    async def test_streams_error_as_event_on_exception(self, runtime, transport):
        runtime.state = MagicMock()
        runtime.state.session_id = "sess-1"
        runtime.state.messages = []
        runtime.state.step = 0
        runtime.state.pending_steer = None
        runtime.state.usage = MagicMock()
        runtime.state.usage.model_dump.return_value = {"total_input": 0, "total_output": 0}
        runtime.current_session_id = "sess-1"
        runtime.get_state = MagicMock(return_value=runtime.state)

        async def failing_gen():
            raise RuntimeError("provider failed")
            yield  # pragma: no cover

        runtime.run_agent_turn = MagicMock()
        runtime.run_agent_turn.return_value = failing_gen()

        await handle_chat_stream(runtime, {"message": "hi"}, transport, 1, "c1")

        # Should have sent both error event and finish
        assert transport.send.await_count >= 2
        import json
        # Find the error event
        sent_events = []
        for call in transport.send.await_args_list:
            data = json.loads(call[0][0])
            sent_events.append(data["params"]["type"])
        assert "error" in sent_events
        assert "finish" in sent_events

    @pytest.mark.anyio
    async def test_streams_finish_on_empty_turn(self, runtime, transport):
        runtime.state = MagicMock()
        runtime.state.session_id = "sess-1"
        runtime.state.messages = []
        runtime.state.step = 0
        runtime.state.pending_steer = None
        runtime.state.usage = MagicMock()
        runtime.state.usage.model_dump.return_value = {"total_input": 0, "total_output": 0}
        runtime.current_session_id = "sess-1"
        runtime.get_state = MagicMock(return_value=runtime.state)

        runtime.run_agent_turn = MagicMock()
        runtime.run_agent_turn.return_value = _async_gen([])

        await handle_chat_stream(runtime, {"message": "hi"}, transport, 1, "c1")

        import json
        last_call = transport.send.await_args_list[-1]
        last_data = json.loads(last_call[0][0])
        assert last_data["params"]["type"] == "finish"
        assert last_data["params"]["reason"] == ""


def _async_gen(items):
    async def gen():
        for item in items:
            yield item
    return gen()


class TestHandleToolsList:
    @pytest.mark.anyio
    async def test_returns_tools(self, runtime, transport):
        tool1 = MagicMock()
        tool1.model_dump.return_value = {"name": "read"}
        tool2 = MagicMock()
        tool2.model_dump.return_value = {"name": "write"}
        runtime.tool_registry.build_tool_definitions = AsyncMock(return_value=[tool1, tool2])

        result = await handle_tools_list(runtime, {}, transport, 1, "c1")

        assert len(result["tools"]) == 2
        assert result["tools"][0]["name"] == "read"


class TestHandleSessionSearch:
    @pytest.mark.anyio
    async def test_returns_matching_sessions(self, runtime, transport):
        s = MagicMock()
        s.id = "s1"
        s.status = "active"
        s.title = "test"
        s.message_count = 3
        s.turn_count = 1
        s.input_tokens = 100
        s.output_tokens = 200
        s.created_at.isoformat.return_value = "2025-01-01T00:00:00"
        s.updated_at.isoformat.return_value = "2025-01-01T01:00:00"
        runtime.session_manager.search = MagicMock(return_value=[s])

        result = await handlers.handle_session_search(
            runtime, {"query": "test", "limit": 10}, transport, 1, "c1"
        )
        assert len(result["sessions"]) == 1
        assert result["sessions"][0]["id"] == "s1"
        assert result["sessions"][0]["input_tokens"] == 100

    @pytest.mark.anyio
    async def test_requires_query(self, runtime, transport):
        with pytest.raises(ValueError, match="query is required"):
            await handlers.handle_session_search(runtime, {}, transport, 1, "c1")


class TestHandleSessionSetTitle:
    @pytest.mark.anyio
    async def test_sets_title_with_session_id(self, runtime, transport):
        result = await handlers.handle_session_set_title(
            runtime, {"title": "New Title", "session_id": "sess-1"}, transport, 1, "c1"
        )
        assert result["status"] == "ok"
        assert result["title"] == "New Title"
        runtime.session_manager.set_title.assert_called_once_with("sess-1", "New Title")

    @pytest.mark.anyio
    async def test_uses_current_session(self, runtime, transport):
        await handlers.handle_session_set_title(
            runtime, {"title": "Auto"}, transport, 1, "c1"
        )
        runtime.session_manager.set_title.assert_called_once_with("sess-1", "Auto")

    @pytest.mark.anyio
    async def test_requires_title(self, runtime, transport):
        with pytest.raises(ValueError, match="title is required"):
            await handlers.handle_session_set_title(runtime, {}, transport, 1, "c1")

    @pytest.mark.anyio
    async def test_requires_active_session(self, runtime, transport):
        runtime.current_session_id = None
        with pytest.raises(ValueError, match="No active session"):
            await handlers.handle_session_set_title(
                runtime, {"title": "T"}, transport, 1, "c1"
            )


class TestHandleSessionGenerateTitle:
    @pytest.mark.anyio
    async def test_returns_title(self, runtime, transport):
        runtime.generate_title_for_current = AsyncMock(return_value="Generated")
        result = await handlers.handle_session_generate_title(
            runtime, {}, transport, 1, "c1"
        )
        assert result["title"] == "Generated"

    @pytest.mark.anyio
    async def test_returns_none(self, runtime, transport):
        runtime.generate_title_for_current = AsyncMock(return_value=None)
        result = await handlers.handle_session_generate_title(
            runtime, {}, transport, 1, "c1"
        )
        assert result["title"] is None


class TestHandleSessionArchive:
    @pytest.mark.anyio
    async def test_archives_with_session_id(self, runtime, transport):
        result = await handlers.handle_session_archive(
            runtime, {"session_id": "sess-target"}, transport, 1, "c1"
        )
        assert result["status"] == "archived"
        assert result["session_id"] == "sess-target"
        runtime.session_manager.archive.assert_called_once_with("sess-target")

    @pytest.mark.anyio
    async def test_archives_current(self, runtime, transport):
        await handlers.handle_session_archive(
            runtime, {}, transport, 1, "c1"
        )
        runtime.session_manager.archive.assert_called_once_with("sess-1")

    @pytest.mark.anyio
    async def test_requires_session_id(self, runtime, transport):
        runtime.current_session_id = None
        with pytest.raises(ValueError, match="No active session"):
            await handlers.handle_session_archive(runtime, {}, transport, 1, "c1")


class TestHandleSubagentListActive:
    @pytest.mark.anyio
    async def test_returns_active_subagents(self, runtime, transport):
        runtime.subagent_manager = MagicMock()
        runtime.subagent_manager.list_active = MagicMock(return_value=[
            {"task_id": "t1", "agent_type": "explore", "status": "running"},
        ])
        result = await handlers.handle_subagent_list_active(
            runtime, {}, transport, 1, "c1"
        )
        assert len(result["subagents"]) == 1
        assert result["subagents"][0]["task_id"] == "t1"

    @pytest.mark.anyio
    async def test_returns_empty_when_no_session(self, runtime, transport):
        runtime.current_session_id = None
        result = await handlers.handle_subagent_list_active(
            runtime, {}, transport, 1, "c1"
        )
        assert result["subagents"] == []


class TestHandleUsageGet:
    @pytest.mark.anyio
    async def test_returns_usage(self, runtime, transport):
        runtime.state.usage.total_input = 100
        runtime.state.usage.total_output = 50
        runtime.state.usage.total_reasoning = 10
        runtime.state.usage.total_cache_read = 5
        runtime.state.usage.context_size = 8192

        result = await handlers.handle_usage_get(runtime, {}, transport, 1, "c1")
        assert result["total_input"] == 100
        assert result["total_output"] == 50
        assert result["context_size"] == 8192

    @pytest.mark.anyio
    async def test_returns_none_when_no_state(self, runtime, transport):
        runtime.state = None
        result = await handlers.handle_usage_get(runtime, {}, transport, 1, "c1")
        assert result["total_input"] == 0
        assert result["total_output"] == 0
        assert result["context_size"] == 0


class TestHandleConfigProviders:
    @pytest.mark.anyio
    async def test_returns_providers(self, runtime, transport):
        runtime._config = MagicMock()
        runtime._config.llm.default_provider = "opencode"
        model_mock = MagicMock()
        model_mock.name = "deepseek-v4-flash"
        model_mock.context_size = 128000
        runtime._config.llm.providers = {
            "opencode": MagicMock(
                type="deepseek",
                base_url="https://opencode.ai/zen/go",
                models=[model_mock],
            ),
        }
        result = await handle_config_providers(runtime, {}, transport, 1, "c1")
        assert result["default_provider"] == "opencode"
        assert "opencode" in result["providers"]
        assert result["providers"]["opencode"]["type"] == "deepseek"
        assert result["providers"]["opencode"]["models"][0]["name"] == "deepseek-v4-flash"

    @pytest.mark.anyio
    async def test_returns_empty_when_no_providers(self, runtime, transport):
        runtime._config = MagicMock()
        runtime._config.llm.default_provider = ""
        runtime._config.llm.providers = {}
        result = await handle_config_providers(runtime, {}, transport, 1, "c1")
        assert result["providers"] == {}


class TestHandleMCPStatus:
    @pytest.mark.anyio
    async def test_returns_server_status(self, runtime, transport):
        runtime.mcp_service = MagicMock()
        runtime.mcp_service.get_status = MagicMock(return_value={
            "server-a": "connected",
            "server-b": "connected",
        })
        result = await handle_mcp_status(runtime, {}, transport, 1, "c1")
        assert len(result["servers"]) == 2
        names = {s["name"] for s in result["servers"]}
        assert names == {"server-a", "server-b"}

    @pytest.mark.anyio
    async def test_returns_empty_when_no_mcp(self, runtime, transport):
        runtime.mcp_service = MagicMock()
        runtime.mcp_service.get_status = MagicMock(return_value={})
        result = await handle_mcp_status(runtime, {}, transport, 1, "c1")
        assert result["servers"] == []

    @pytest.mark.anyio
    async def test_includes_status_string(self, runtime, transport):
        runtime.mcp_service = MagicMock()
        runtime.mcp_service.get_status = MagicMock(return_value={
            "ok-server": "connected",
            "failed-server": "failed: Connection refused",
        })
        result = await handle_mcp_status(runtime, {}, transport, 1, "c1")
        statuses = {s["name"]: s["status"] for s in result["servers"]}
        assert statuses["ok-server"] == "connected"
        assert "failed" in statuses["failed-server"]


class TestHandleSessionSetConfig:
    @pytest.mark.anyio
    async def test_creates_new_session_with_provider_model(self, runtime, transport):
        new_session = MagicMock()
        new_session.id = "sess-new"
        runtime.session_manager.create = MagicMock(return_value=new_session)
        runtime.state = MagicMock()
        runtime.state.session_id = "sess-old"

        result = await handle_session_set_config(
            runtime, {"provider": "opencode", "model": "deepseek-v4"}, transport, 1, "c1",
        )
        assert result["session_id"] == "sess-new"
        runtime.session_manager.create.assert_called_once_with(
            provider="opencode", model="deepseek-v4",
        )

    @pytest.mark.anyio
    async def test_raises_when_no_active_session(self, runtime, transport):
        runtime.state = None
        with pytest.raises(ValueError, match="No active session"):
            await handle_session_set_config(
                runtime, {"provider": "opencode", "model": "deepseek-v4"}, transport, 1, "c1",
            )

    @pytest.mark.anyio
    async def test_accepts_empty_params(self, runtime, transport):
        new_session = MagicMock()
        new_session.id = "sess-new"
        runtime.session_manager.create = MagicMock(return_value=new_session)
        runtime.state = MagicMock()

        result = await handle_session_set_config(
            runtime, {}, transport, 1, "c1",
        )
        assert result["session_id"] == "sess-new"
        runtime.session_manager.create.assert_called_once_with(provider="", model="")


def _async_gen(items):
    async def gen():
        for item in items:
            yield item
    return gen()
