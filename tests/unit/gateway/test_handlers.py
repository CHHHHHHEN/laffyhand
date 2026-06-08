from __future__ import annotations

import asyncio
import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from laffyhand.core.llm.specs.models import AssistantMessage, SystemMessage, ToolMessage, UserMessage
from laffyhand.gateway import handlers
from laffyhand.gateway.handlers import (
    handle_initialize,
    handle_shutdown,
    handle_session_create,
    handle_session_list,
    handle_session_load,
    handle_session_delete,
    handle_session_fork,
    handle_session_compact,
    handle_session_subscribe,
    handle_chat,
    handle_chat_stream,
    handle_chat_cancel,
    handle_config_providers,
    handle_mcp_status,
    handle_mcp_add_server,
    handle_mcp_remove_server,
    handle_session_set_config,
    handle_permission_respond,
    handle_tools_list,
    handle_tools_set_disabled,
    handle_workspace_set,
)
from laffyhand.gateway.session_converters import _serialize_messages, _next_msg_id
from laffyhand.core.llm.specs.models import (
    ToolCallContent,
    Usage,
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
    r.context_size = 8192
    r.build_system_prompt = AsyncMock(return_value="You are a helpful assistant.")
    r._generate_title = AsyncMock()
    r._schedule_title_generation = MagicMock()
    r.get_session_lock = MagicMock(return_value=MagicMock())

    _state_backend = {}
    _perm_backend = {}
    r.pending_permissions = _perm_backend
    r.get_state = MagicMock(side_effect=lambda sid: _state_backend.get(sid))

    r.session_store = MagicMock()
    r.session_store._states = _state_backend
    r.session_store.set = MagicMock(side_effect=lambda sid, st: _state_backend.__setitem__(sid, st))
    r.session_store.pop = MagicMock(side_effect=lambda sid: _state_backend.pop(sid, None))
    r.session_store.get = MagicMock(side_effect=lambda sid: _state_backend.get(sid))
    r.session_store.pending_permissions = _perm_backend

    r.session_event_bus = MagicMock()
    r.session_event_bus.publish = AsyncMock()
    r.session_event_bus.close_session = AsyncMock()
    r.session_event_bus.subscribe = AsyncMock()
    r.session_event_bus.unsubscribe = AsyncMock()
    r.session_event_bus.has_subscribers = AsyncMock(return_value=False)
    return r


class TestHandleInitialize:
    @pytest.mark.anyio
    async def test_returns_server_info(self, runtime, transport):
        result = await handle_initialize(runtime, {}, transport, 1, "c1")
        assert result["protocol_version"] == "2.0"
        assert result["server_info"]["name"] == "laffyhand"
        assert result["session_id"] is None


class TestHandleShutdown:
    @pytest.mark.anyio
    async def test_calls_runtime_shutdown(self, runtime, transport):
        runtime.shutdown = AsyncMock()
        await handle_shutdown(runtime, {}, transport, 1, "c1")
        runtime.shutdown.assert_awaited_once()


class TestHandleSessionCreate:
    @pytest.mark.anyio
    async def test_creates_and_returns_session(self, runtime, transport):
        result = await handle_session_create(runtime, {}, transport, 1, "c1")

        assert result["session_id"] is not None and isinstance(result["session_id"], str)
        runtime.session_manager.set_pending_meta.assert_called_once()
        runtime._schedule_title_generation.assert_called_once_with(
            result["session_id"], "on_create"
        )

    @pytest.mark.anyio
    async def test_returns_session_id(self, runtime, transport):
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
            status=None,
            limit=20,
            offset=0,
        )


class TestHandleSessionLoad:
    @pytest.mark.anyio
    async def test_loads_session(self, runtime, transport):
        mock_state = MagicMock()
        mock_state.session_id = "sess-target"
        mock_state.messages = ["m1", "m2"]
        mock_state.turn_count = 7
        runtime.load_session_state = MagicMock(return_value=mock_state)
        mock_session = MagicMock()
        mock_session.title = "My Session"
        runtime.session_manager.get = MagicMock(return_value=mock_session)

        result = await handle_session_load(
            runtime, {"session_id": "sess-target"}, transport, 1, "c1"
        )

        assert result["session_id"] == "sess-target"
        assert result["title"] == "My Session"
        assert result["messages_count"] == 2
        assert result["turn_count"] == 7

    @pytest.mark.anyio
    async def test_loads_session_without_title(self, runtime, transport):
        mock_state = MagicMock()
        mock_state.session_id = "sess-untitled"
        mock_state.messages = []
        mock_state.turn_count = 0
        runtime.load_session_state = MagicMock(return_value=mock_state)
        runtime.session_manager.get = MagicMock(return_value=None)

        result = await handle_session_load(
            runtime, {"session_id": "sess-untitled"}, transport, 1, "c1"
        )

        assert result["title"] is None

    @pytest.mark.anyio
    async def test_requires_session_id(self, runtime, transport):
        with pytest.raises(ValueError, match="session_id is required"):
            await handle_session_load(runtime, {}, transport, 1, "c1")

    @pytest.mark.anyio
    async def test_raises_on_not_found(self, runtime, transport):
        runtime.load_session_state = MagicMock(return_value=None)
        with pytest.raises(ValueError, match="not found"):
            await handle_session_load(
                runtime, {"session_id": "invalid"}, transport, 1, "c1"
            )


class TestHandleSessionDelete:
    @pytest.mark.anyio
    async def test_deletes_session(self, runtime, transport):
        runtime.session_manager.delete = MagicMock()
        result = await handle_session_delete(
            runtime, {"session_id": "sess-del"}, transport, 1, "c1"
        )
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
        result = await handle_session_fork(runtime, {"session_id": "sess-1"}, transport, 1, "c1")
        assert result["session_id"] == "forked-id"
        runtime.fork_session.assert_called_once_with("sess-1")

    @pytest.mark.anyio
    async def test_uses_session_id(self, runtime, transport):
        runtime.fork_session = MagicMock(return_value="forked-id")
        await handle_session_fork(runtime, {"session_id": "sess-target"}, transport, 1, "c1")
        runtime.fork_session.assert_called_once_with("sess-target")

    @pytest.mark.anyio
    async def test_raises_when_missing_session_id(self, runtime, transport):
        with pytest.raises(ValueError, match="session_id is required"):
            await handle_session_fork(runtime, {}, transport, 1, "c1")

    @pytest.mark.anyio
    async def test_raises_when_fork_returns_none(self, runtime, transport):
        runtime.fork_session = MagicMock(return_value=None)
        with pytest.raises(ValueError, match="not found"):
            await handle_session_fork(runtime, {"session_id": "sess-1"}, transport, 1, "c1")


class TestHandleSessionCompact:
    @pytest.mark.anyio
    async def test_compacts_session(self, runtime, transport):
        runtime.compact_session = AsyncMock(return_value="compacted-id")
        result = await handle_session_compact(
            runtime, {"session_id": "sess-1"}, transport, 1, "c1"
        )
        assert result["status"] == "compacted"
        assert result["session_id"] == "compacted-id"
        assert result["parent_id"] == "sess-1"
        runtime.compact_session.assert_awaited_once_with("sess-1")

    @pytest.mark.anyio
    async def test_requires_session_id(self, runtime, transport):
        with pytest.raises(ValueError, match="session_id is required"):
            await handle_session_compact(runtime, {}, transport, 1, "c1")

    @pytest.mark.anyio
    async def test_returns_nothing_to_compact_when_noop(self, runtime, transport):
        runtime.compact_session = AsyncMock(return_value=None)
        result = await handle_session_compact(
            runtime, {"session_id": "sess-1"}, transport, 1, "c1"
        )
        assert result["status"] == "nothing_to_compact"
        assert result["session_id"] == "sess-1"
        assert result["parent_id"] is None
        runtime.compact_session.assert_awaited_once_with("sess-1")


class TestHandleChat:
    @pytest.mark.anyio
    async def test_requires_message(self, runtime, transport):
        with pytest.raises(ValueError, match="message is required"):
            await handle_chat(runtime, {}, transport, 1, "c1")

    @pytest.mark.anyio
    async def test_chat_with_existing_session(self, runtime, transport):
        mock_state = MagicMock()
        mock_state.session_id = "sess-1"
        mock_state.messages = []
        mock_state.step = 0
        runtime.get_state = MagicMock(return_value=mock_state)

        events = []
        runtime.run_agent_turn = MagicMock()
        runtime.run_agent_turn.return_value = _async_gen(events)

        result = await handle_chat(
            runtime, {"message": "hello", "session_id": "sess-1"}, transport, 1, "c1"
        )

        assert "content" in result
        assert result["session_id"] == "sess-1"
        runtime._generate_title.assert_called_once_with("sess-1", "auto")

    @pytest.mark.anyio
    async def test_chat_with_session_id_in_params(self, runtime, transport):
        """_prepare_chat with session_id uses get_state."""
        mock_state = MagicMock()
        mock_state.session_id = "sess-1"
        mock_state.messages = []
        mock_state.step = 0
        runtime.get_state = MagicMock(return_value=mock_state)

        events = []
        runtime.run_agent_turn = MagicMock()
        runtime.run_agent_turn.return_value = _async_gen(events)

        result = await handle_chat(
            runtime, {"message": "hello", "session_id": "sess-1"}, transport, 1, "c1"
        )

        assert result["session_id"] == "sess-1"

    @pytest.mark.anyio
    async def test_chat_with_session_id_raises_on_not_found(self, runtime, transport):
        """_prepare_chat with unknown session_id should raise."""
        runtime.get_state = MagicMock(return_value=None)
        with pytest.raises(RuntimeError, match="Session state not found"):
            await handle_chat(
                runtime, {"message": "hello", "session_id": "unknown"}, transport, 1, "c1"
            )

    @pytest.mark.anyio
    async def test_chat_without_session_creates_one(self, runtime, transport):
        runtime.run_agent_turn = MagicMock()
        runtime.run_agent_turn.return_value = _async_gen([])

        result = await handle_chat(runtime, {"message": "hello"}, transport, 1, "c1")
        session_id = result["session_id"]
        assert session_id is not None and isinstance(session_id, str)
        runtime.session_manager.set_pending_meta.assert_called_once()
        runtime._schedule_title_generation.assert_any_call(session_id, "on_create")
        runtime._generate_title.assert_any_call(session_id, "auto")


class TestHandleChatCancel:
    @pytest.mark.anyio
    async def test_cancels_by_session(self, runtime, transport):
        """cancel_session_stream is tried first when session_id is present."""
        dispatcher = MagicMock()
        dispatcher.cancel_session_stream = AsyncMock(return_value=True)
        transport.dispatcher = dispatcher
        result = await handle_chat_cancel(runtime, {"session_id": "sess-1"}, transport, 1, "c1")
        assert result["status"] == "cancelled"
        dispatcher.cancel_session_stream.assert_called_once_with("sess-1")

    @pytest.mark.anyio
    async def test_cancels_by_conn_id_when_no_session(self, runtime, transport):
        """Without session_id, falls back to conn_id-based cancel."""
        dispatcher = MagicMock()
        dispatcher.cancel_connection = MagicMock(return_value=True)
        transport.dispatcher = dispatcher
        transport.sse_canceller = None
        result = await handle_chat_cancel(runtime, {}, transport, 1, "c1")
        assert result["status"] == "cancelled"
        dispatcher.cancel_connection.assert_called_once_with("c1")

    @pytest.mark.anyio
    async def test_no_active_stream_when_cancel_fails(self, runtime, transport):
        """Both session and conn_id cancel fail -> no_active_stream."""
        dispatcher = MagicMock()
        dispatcher.cancel_session_stream = AsyncMock(return_value=False)
        dispatcher.cancel_connection = MagicMock(return_value=False)
        transport.dispatcher = dispatcher
        transport.sse_canceller = None
        result = await handle_chat_cancel(runtime, {"session_id": "sess-1"}, transport, 1, "c1")
        assert result["status"] == "no_active_stream"

    @pytest.mark.anyio
    async def test_no_active_stream_when_no_mechanism(self, runtime, transport):
        """No dispatcher or SSE canceller -> no_active_stream."""
        transport.dispatcher = None
        transport.sse_canceller = None
        result = await handle_chat_cancel(runtime, {}, transport, 1, "c1")
        assert result["status"] == "no_active_stream"


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
        result = _serialize_messages(
            [AssistantMessage(content="answer", reasoning="thinking...")]
        )
        assert result[0]["reasoning"] == "thinking..."

    def test_assistant_message_with_tool_calls(self):
        tc = ToolCallContent(
            tool_call_id="call-1", tool_name="read_file", args='{"path": "/test"}'
        )
        result = _serialize_messages(
            [AssistantMessage(content="using tool", tool_calls=[tc])]
        )
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

    def test_tool_message_skipped(self):
        # ToolMessage entries are skipped — content is embedded in AssistantMessage
        result = _serialize_messages(
            [ToolMessage(content="tool output", tool_call_id="call-1")]
        )
        assert len(result) == 0

    def test_tool_result_embedded_in_assistant(self):
        msgs = [
            AssistantMessage(
                content="",
                tool_calls=[
                    ToolCallContent(
                        tool_call_id="call-1",
                        tool_name="read_file",
                        args='{"path": "/test"}',
                    )
                ],
            ),
            ToolMessage(content="file content", tool_call_id="call-1"),
        ]
        result = _serialize_messages(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["toolCalls"] == [
            {
                "id": "call-1",
                "name": "read_file",
                "arguments": '{"path": "/test"}',
                "status": "completed",
                "result": "file content",
                "isError": False,
            }
        ]

    def test_tool_result_embedded_is_error(self):
        msgs = [
            AssistantMessage(
                content="",
                tool_calls=[
                    ToolCallContent(
                        tool_call_id="call-1",
                        tool_name="read_file",
                        args='{"path": "/test"}',
                    )
                ],
            ),
            ToolMessage(content="error msg", tool_call_id="call-1", is_error=True),
        ]
        result = _serialize_messages(msgs)
        assert result[0]["toolCalls"][0]["status"] == "error"
        assert result[0]["toolCalls"][0]["isError"] is True
        assert result[0]["toolCalls"][0]["result"] == "error msg"

    def test_tool_call_without_result_has_pending_status(self):
        msgs = [
            AssistantMessage(
                content="",
                tool_calls=[
                    ToolCallContent(
                        tool_call_id="call-1",
                        tool_name="read_file",
                        args='{"path": "/test"}',
                    )
                ],
            ),
        ]
        result = _serialize_messages(msgs)
        assert result[0]["toolCalls"][0]["status"] == "pending"
        assert "result" not in result[0]["toolCalls"][0]

    def test_mixed_messages(self):
        msgs = [
            SystemMessage(content="sys"),
            UserMessage(content="user"),
            AssistantMessage(content="assistant"),
            ToolMessage(content="result", tool_call_id="c1"),
        ]
        result = _serialize_messages(msgs)
        # ToolMessage is skipped
        assert len(result) == 3
        assert [m["role"] for m in result] == ["system", "user", "assistant"]

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
        assert id1 != id2
        # Extract counter suffix to verify monotonic increment
        parts1 = id1.split("-")
        parts2 = id2.split("-")
        assert int(parts2[-1]) == int(parts1[-1]) + 1


class TestHandleSessionLoadWithMessages:
    @pytest.mark.anyio
    async def test_returns_messages(self, runtime, transport):
        mock_state = MagicMock()
        mock_state.session_id = "sess-target"
        mock_state.messages = [
            UserMessage(content="hello"),
            AssistantMessage(content="hi there"),
        ]
        mock_state.turn_count = 2
        runtime.load_session_state = MagicMock(return_value=mock_state)
        mock_session = MagicMock()
        mock_session.title = "Chat Title"
        runtime.session_manager.get = MagicMock(return_value=mock_session)

        result = await handle_session_load(
            runtime, {"session_id": "sess-target"}, transport, 1, "c1"
        )

        assert result["title"] == "Chat Title"
        assert "messages" in result
        assert len(result["messages"]) == 2
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"


class TestHandleChatStream:
    @pytest.mark.anyio
    async def test_streams_events_and_finish(self, runtime, transport):
        from laffyhand.core.models import TextDelta

        mock_state = MagicMock()
        mock_state.session_id = "sess-1"
        mock_state.messages = []
        mock_state.step = 0
        mock_state.pending_steer = None
        mock_state.usage = MagicMock()
        mock_state.usage.model_dump.return_value = {
            "total_input": 0,
            "total_output": 0,
        }
        runtime.get_state = MagicMock(return_value=mock_state)

        runtime.run_agent_turn = MagicMock()
        runtime.run_agent_turn.return_value = _async_gen(
            [TextDelta(id="t1", text="hello")]
        )
        runtime.subagent_manager = None

        await handle_chat_stream(
            runtime, {"message": "hi", "session_id": "sess-1"}, transport, 1, "c1"
        )

        runtime._generate_title.assert_called_once_with("sess-1", "auto")

        # Should have sent at least 2 messages: event + finish
        assert transport.send.await_count >= 2
        # The finish should be the last call
        last_call = transport.send.await_args_list[-1]
        import json

        last_data = json.loads(last_call[0][0])
        assert last_data["params"]["type"] == "finish"

    @pytest.mark.anyio
    async def test_streams_error_as_event_on_exception(self, runtime, transport):
        mock_state = MagicMock()
        mock_state.session_id = "sess-1"
        mock_state.messages = []
        mock_state.step = 0
        mock_state.pending_steer = None
        mock_state.usage = MagicMock()
        mock_state.usage.model_dump.return_value = {
            "total_input": 0,
            "total_output": 0,
        }
        runtime.get_state = MagicMock(return_value=mock_state)

        async def failing_gen():
            raise RuntimeError("provider failed")
            yield  # pragma: no cover

        runtime.run_agent_turn = MagicMock()
        runtime.run_agent_turn.return_value = failing_gen()
        runtime.subagent_manager = None

        await handle_chat_stream(
            runtime, {"message": "hi", "session_id": "sess-1"}, transport, 1, "c1"
        )

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
        mock_state = MagicMock()
        mock_state.session_id = "sess-1"
        mock_state.messages = []
        mock_state.step = 0
        mock_state.pending_steer = None
        mock_state.usage = MagicMock()
        mock_state.usage.model_dump.return_value = {
            "total_input": 0,
            "total_output": 0,
        }
        runtime.get_state = MagicMock(return_value=mock_state)

        runtime.run_agent_turn = MagicMock()
        runtime.run_agent_turn.return_value = _async_gen([])
        runtime.subagent_manager = None

        await handle_chat_stream(
            runtime, {"message": "hi", "session_id": "sess-1"}, transport, 1, "c1"
        )

        import json

        last_call = transport.send.await_args_list[-1]
        last_data = json.loads(last_call[0][0])
        assert last_data["params"]["type"] == "finish"
        assert last_data["params"]["reason"] == ""


class TestHandleSessionSubscribe:
    @pytest.mark.anyio
    async def test_subscribes_and_receives_events(self, runtime, transport):
        session_id = "sess-sub"
        mock_state = MagicMock()
        mock_state.session_id = session_id
        runtime.get_state = MagicMock(return_value=mock_state)
        runtime.load_session_state = MagicMock(return_value=mock_state)

        real_queue: asyncio.Queue[dict | None] = asyncio.Queue()
        runtime.session_event_bus.subscribe = AsyncMock(return_value=real_queue)

        async def run_subscriber():
            await handle_session_subscribe(
                runtime, {"session_id": session_id}, transport, 1, "c1",
            )

        async def publish_events():
            await asyncio.sleep(0.05)
            await real_queue.put({"type": "text-delta", "text": "hello"})
            await asyncio.sleep(0.05)
            await real_queue.put({"type": "finish"})
            await asyncio.sleep(0.05)
            await real_queue.put(None)

        async with asyncio.TaskGroup() as tg:
            tg.create_task(run_subscriber())
            tg.create_task(publish_events())

        assert transport.send.call_count >= 2
        calls = transport.send.await_args_list
        sent_data = [json.loads(c[0][0]) for c in calls]

        events = [n["params"] for n in sent_data if n.get("method") == "event"]
        assert {"type": "text-delta", "text": "hello"} in events
        assert {"type": "finish"} in events

    @pytest.mark.anyio
    async def test_missing_session_id_raises(self, runtime, transport):
        with pytest.raises(ValueError, match="session_id is required"):
            await handle_session_subscribe(runtime, {}, transport, 1, "c1")

    @pytest.mark.anyio
    async def test_session_not_found_raises(self, runtime, transport):
        runtime.load_session_state = MagicMock(return_value=None)
        runtime.get_state = MagicMock(return_value=None)
        with pytest.raises(ValueError, match="Session not found"):
            await handle_session_subscribe(
                runtime, {"session_id": "nonexistent"}, transport, 1, "c1",
            )

    @pytest.mark.anyio
    async def test_unsubscribe_on_cancellation(self, runtime, transport):
        session_id = "sess-cancel"
        mock_state = MagicMock()
        mock_state.session_id = session_id
        runtime.get_state = MagicMock(return_value=mock_state)
        runtime.load_session_state = MagicMock(return_value=mock_state)

        real_queue: asyncio.Queue[dict | None] = asyncio.Queue()
        runtime.session_event_bus.subscribe = AsyncMock(return_value=real_queue)

        async def run_and_cancel():
            task = asyncio.create_task(
                handle_session_subscribe(
                    runtime, {"session_id": session_id}, transport, 1, "c1",
                ),
            )
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        await run_and_cancel()
        runtime.session_event_bus.unsubscribe.assert_awaited_once()


class TestHandleToolsList:
    @pytest.mark.anyio
    async def test_returns_tools_with_enabled_field(self, runtime, transport):
        mock_state = MagicMock()
        mock_state.disabled_tools = set()
        runtime.get_state = MagicMock(return_value=mock_state)
        tool1 = MagicMock()
        tool1.name = "read"
        tool1.description = "Read file"
        tool1.input_schema = {}
        tool2 = MagicMock()
        tool2.name = "write"
        tool2.description = "Write file"
        tool2.input_schema = {}
        runtime.tool_registry.build_tool_definitions = AsyncMock(
            return_value=[tool1, tool2]
        )

        result = await handle_tools_list(
            runtime, {"session_id": "sess-1"}, transport, 1, "c1"
        )

        assert len(result["tools"]) == 2
        assert result["tools"][0]["name"] == "read"
        assert result["tools"][0]["enabled"] is True

    @pytest.mark.anyio
    async def test_reflects_disabled_tools(self, runtime, transport):
        mock_state = MagicMock()
        mock_state.disabled_tools = {"read"}
        runtime.get_state = MagicMock(return_value=mock_state)
        tool1 = MagicMock()
        tool1.name = "read"
        tool1.description = "Read file"
        tool1.input_schema = {}
        tool2 = MagicMock()
        tool2.name = "write"
        tool2.description = "Write file"
        tool2.input_schema = {}
        runtime.tool_registry.build_tool_definitions = AsyncMock(
            return_value=[tool1, tool2]
        )

        result = await handle_tools_list(
            runtime, {"session_id": "sess-1"}, transport, 1, "c1"
        )

        tools = {t["name"]: t["enabled"] for t in result["tools"]}
        assert tools["read"] is False
        assert tools["write"] is True


class TestHandleToolsSetDisabled:
    @pytest.mark.anyio
    async def test_sets_disabled_tools(self, runtime, transport):
        mock_state = MagicMock()
        mock_state.disabled_tools = set()
        runtime.get_state = MagicMock(return_value=mock_state)
        result = await handle_tools_set_disabled(
            runtime, {"tool_names": ["read", "write"], "session_id": "sess-1"}, transport, 1, "c1"
        )
        assert result["status"] == "ok"
        assert set(result["disabled_tools"]) == {"read", "write"}
        assert mock_state.disabled_tools == {"read", "write"}

    @pytest.mark.anyio
    async def test_clears_disabled_tools(self, runtime, transport):
        mock_state = MagicMock()
        mock_state.disabled_tools = {"read", "write"}
        runtime.get_state = MagicMock(return_value=mock_state)
        result = await handle_tools_set_disabled(
            runtime, {"tool_names": [], "session_id": "sess-1"}, transport, 1, "c1"
        )
        assert result["status"] == "ok"
        assert mock_state.disabled_tools == set()

    @pytest.mark.anyio
    async def test_raises_when_no_state(self, runtime, transport):
        runtime.get_state = MagicMock(return_value=None)
        with pytest.raises(RuntimeError, match="Session not found"):
            await handle_tools_set_disabled(
                runtime, {"tool_names": [], "session_id": "sess-1"}, transport, 1, "c1"
            )


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
    async def test_uses_session_id(self, runtime, transport):
        await handlers.handle_session_set_title(
            runtime, {"title": "Auto", "session_id": "sess-1"}, transport, 1, "c1"
        )
        runtime.session_manager.set_title.assert_called_once_with("sess-1", "Auto")

    @pytest.mark.anyio
    async def test_requires_title(self, runtime, transport):
        with pytest.raises(ValueError, match="title is required"):
            await handlers.handle_session_set_title(runtime, {}, transport, 1, "c1")

    @pytest.mark.anyio
    async def test_requires_session_id(self, runtime, transport):
        with pytest.raises(ValueError, match="session_id is required"):
            await handlers.handle_session_set_title(
                runtime, {"title": "T"}, transport, 1, "c1"
            )


class TestHandleSessionGenerateTitle:
    @pytest.mark.anyio
    async def test_returns_title(self, runtime, transport):
        runtime._do_generate_title = AsyncMock(return_value="Generated")
        result = await handlers.handle_session_generate_title(
            runtime, {"session_id": "sess-1"}, transport, 1, "c1"
        )
        assert result["title"] == "Generated"
        runtime._do_generate_title.assert_awaited_once_with("sess-1")

    @pytest.mark.anyio
    async def test_returns_none(self, runtime, transport):
        runtime._do_generate_title = AsyncMock(return_value=None)
        result = await handlers.handle_session_generate_title(
            runtime, {"session_id": "sess-1"}, transport, 1, "c1"
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
    async def test_requires_session_id(self, runtime, transport):
        with pytest.raises(ValueError, match="session_id is required"):
            await handlers.handle_session_archive(runtime, {}, transport, 1, "c1")


class TestHandleSubagentListActive:
    @pytest.mark.anyio
    async def test_returns_active_subagents(self, runtime, transport):
        runtime.subagent_manager = MagicMock()
        runtime.subagent_manager.list_active = MagicMock(
            return_value=[
                {"task_id": "t1", "agent_type": "explore", "status": "running"},
            ]
        )
        result = await handlers.handle_subagent_list_active(
            runtime, {"session_id": "sess-1"}, transport, 1, "c1"
        )
        assert len(result["subagents"]) == 1
        assert result["subagents"][0]["task_id"] == "t1"

    @pytest.mark.anyio
    async def test_returns_empty_when_no_session(self, runtime, transport):
        result = await handlers.handle_subagent_list_active(
            runtime, {}, transport, 1, "c1"
        )
        assert result["subagents"] == []


class TestHandleUsageGet:
    @pytest.mark.anyio
    async def test_returns_usage(self, runtime, transport):
        mock_usage = MagicMock()
        mock_usage.total_input = 100
        mock_usage.total_output = 50
        mock_usage.total_reasoning = 10
        mock_usage.total_cache_read = 5
        mock_usage.context_size = 8192
        mock_state = MagicMock()
        mock_state.usage = mock_usage
        runtime.get_state = MagicMock(return_value=mock_state)

        result = await handlers.handle_usage_get(
            runtime, {"session_id": "sess-1"}, transport, 1, "c1"
        )
        assert result["total_input"] == 100
        assert result["total_output"] == 50
        assert result["context_size"] == 8192

    @pytest.mark.anyio
    async def test_returns_none_when_no_state(self, runtime, transport):
        result = await handlers.handle_usage_get(runtime, {}, transport, 1, "c1")
        assert result["total_input"] == 0
        assert result["total_output"] == 0
        assert result["context_size"] == 0


class TestHandleConfigProviders:
    @pytest.mark.anyio
    async def test_returns_providers(self, runtime, transport):
        runtime.config = MagicMock()
        runtime.config.llm.default_provider = "opencode"
        model_mock = MagicMock()
        model_mock.name = "deepseek-v4-flash"
        model_mock.context_size = 1000000
        runtime.config.llm.providers = {
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
        assert (
            result["providers"]["opencode"]["models"][0]["name"] == "deepseek-v4-flash"
        )

    @pytest.mark.anyio
    async def test_returns_empty_when_no_providers(self, runtime, transport):
        runtime.config = MagicMock()
        runtime.config.llm.default_provider = ""
        runtime.config.llm.providers = {}
        result = await handle_config_providers(runtime, {}, transport, 1, "c1")
        assert result["providers"] == {}


class TestHandleMCPStatus:
    @pytest.mark.anyio
    async def test_returns_server_status(self, runtime, transport):
        runtime.mcp_service = MagicMock()
        runtime.mcp_service.get_status = MagicMock(
            return_value={
                "server-a": "connected",
                "server-b": "connected",
            }
        )
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
        runtime.mcp_service.get_status = MagicMock(
            return_value={
                "ok-server": "connected",
                "failed-server": "failed: Connection refused",
            }
        )
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
        mock_state = MagicMock()
        mock_state.session_id = "sess-old"
        runtime.get_state = MagicMock(return_value=mock_state)

        result = await handle_session_set_config(
            runtime,
            {"provider": "opencode", "model": "deepseek-v4", "session_id": "sess-1"},
            transport,
            1,
            "c1",
        )
        assert result["session_id"] == "sess-new"
        runtime.session_manager.create.assert_called_once_with(
            provider="opencode",
            model="deepseek-v4",
        )

    @pytest.mark.anyio
    async def test_raises_when_no_session_id(self, runtime, transport):
        with pytest.raises(ValueError, match="session_id is required"):
            await handle_session_set_config(
                runtime,
                {"provider": "opencode", "model": "deepseek-v4"},
                transport,
                1,
                "c1",
            )

    @pytest.mark.anyio
    async def test_raises_when_session_not_found(self, runtime, transport):
        runtime.get_state = MagicMock(return_value=None)
        with pytest.raises(RuntimeError, match="Session not found"):
            await handle_session_set_config(
                runtime,
                {"provider": "opencode", "model": "deepseek-v4", "session_id": "sess-1"},
                transport,
                1,
                "c1",
            )

    @pytest.mark.anyio
    async def test_accepts_empty_params(self, runtime, transport):
        new_session = MagicMock()
        new_session.id = "sess-new"
        runtime.session_manager.create = MagicMock(return_value=new_session)
        mock_state = MagicMock()
        runtime.get_state = MagicMock(return_value=mock_state)

        result = await handle_session_set_config(
            runtime,
            {"session_id": "sess-1"},
            transport,
            1,
            "c1",
        )
        assert result["session_id"] == "sess-new"
        runtime.session_manager.create.assert_called_once_with(provider="", model="")


class TestHandlePermissionRespond:
    @pytest.fixture
    def runtime_with_pending(self, runtime):
        runtime.pending_permissions = {}
        runtime.session_store.pending_permissions = runtime.pending_permissions
        runtime.tool_registry = MagicMock()
        runtime.tool_registry.permission = MagicMock()
        runtime.tool_registry.permission._rules = {}
        return runtime

    @pytest.mark.anyio
    async def test_allow_resolves_true(self, runtime_with_pending, transport):
        event = asyncio.Event()
        runtime_with_pending.pending_permissions["req-1"] = (
            event,
            "skill",
            "test-tool",
            None,
            None,
        )
        result = await handle_permission_respond(
            runtime_with_pending,
            {"request_id": "req-1", "action": "allow"},
            transport,
            1,
            "c1",
        )
        assert result["status"] == "ok"
        assert event.is_set()
        _, _, _, stored_result, stored_reason = runtime_with_pending.pending_permissions.get(
            "req-1", (None, None, None, None, None)
        )
        assert stored_result is True
        assert stored_reason is None

    @pytest.mark.anyio
    async def test_deny_resolves_false(self, runtime_with_pending, transport):
        event = asyncio.Event()
        runtime_with_pending.pending_permissions["req-1"] = (
            event,
            "skill",
            "test-tool",
            None,
            None,
        )
        result = await handle_permission_respond(
            runtime_with_pending,
            {"request_id": "req-1", "action": "deny"},
            transport,
            1,
            "c1",
        )
        assert result["status"] == "ok"
        assert event.is_set()
        _, _, _, stored_result, stored_reason = runtime_with_pending.pending_permissions.get(
            "req-1", (None, None, None, None, None)
        )
        assert stored_result is False
        assert stored_reason is None

    @pytest.mark.anyio
    async def test_deny_with_reason(self, runtime_with_pending, transport):
        event = asyncio.Event()
        runtime_with_pending.pending_permissions["req-1"] = (
            event,
            "skill",
            "test-tool",
            None,
            None,
        )
        result = await handle_permission_respond(
            runtime_with_pending,
            {"request_id": "req-1", "action": "deny", "reason": "not needed"},
            transport,
            1,
            "c1",
        )
        assert result["status"] == "ok"
        assert event.is_set()
        _, _, _, stored_result, stored_reason = runtime_with_pending.pending_permissions.get(
            "req-1", (None, None, None, None, None)
        )
        assert stored_result is False
        assert stored_reason == "not needed"

    @pytest.mark.anyio
    async def test_always_sets_rule_and_resolves_true(
        self, runtime_with_pending, transport
    ):
        event = asyncio.Event()
        runtime_with_pending.pending_permissions["req-1"] = (
            event,
            "skill",
            "test-tool",
            None,
            None,
        )
        result = await handle_permission_respond(
            runtime_with_pending,
            {"request_id": "req-1", "action": "always"},
            transport,
            1,
            "c1",
        )
        assert result["status"] == "ok"
        assert event.is_set()
        runtime_with_pending.tool_registry.permission.add_rule.assert_called_with(
            "skill:test-tool", "allow"
        )
        _, _, _, stored_result, stored_reason = runtime_with_pending.pending_permissions.get(
            "req-1", (None, None, None, None, None)
        )
        assert stored_result is True
        assert stored_reason is None

    @pytest.mark.anyio
    async def test_unknown_request_id_raises(self, runtime_with_pending, transport):
        runtime_with_pending.pending_permissions = {}
        with pytest.raises(ValueError, match="Unknown or expired"):
            await handle_permission_respond(
                runtime_with_pending,
                {"request_id": "nonexistent", "action": "allow"},
                transport,
                1,
                "c1",
            )

    @pytest.mark.anyio
    async def test_invalid_action_raises(self, runtime_with_pending, transport):
        event = asyncio.Event()
        runtime_with_pending.pending_permissions["req-1"] = (
            event,
            "skill",
            "test-tool",
            None,
            None,
        )
        with pytest.raises(ValueError, match="Invalid permission action"):
            await handle_permission_respond(
                runtime_with_pending,
                {"request_id": "req-1", "action": "invalid"},
                transport,
                1,
                "c1",
            )


class TestHandleMCPAddServer:
    @pytest.mark.anyio
    async def test_adds_local_server(self, runtime, transport):
        runtime.add_mcp_server = AsyncMock(return_value=["mcp_test_tool1"])
        result = await handle_mcp_add_server(
            runtime,
            {"name": "test-server", "type": "local", "command": ["echo", "hi"]},
            transport, 1, "c1",
        )
        assert result["status"] == "connected"
        assert result["name"] == "test-server"
        assert result["tools"] == ["mcp_test_tool1"]

    @pytest.mark.anyio
    async def test_adds_remote_server(self, runtime, transport):
        runtime.add_mcp_server = AsyncMock(return_value=["mcp_remote_tool1"])
        result = await handle_mcp_add_server(
            runtime,
            {"name": "remote-server", "type": "remote", "url": "https://example.com/mcp"},
            transport, 1, "c1",
        )
        assert result["status"] == "connected"
        assert result["name"] == "remote-server"

    @pytest.mark.anyio
    async def test_requires_name(self, runtime, transport):
        with pytest.raises(ValueError, match="name is required"):
            await handle_mcp_add_server(
                runtime, {}, transport, 1, "c1",
            )

    @pytest.mark.anyio
    async def test_requires_command_for_local(self, runtime, transport):
        with pytest.raises(ValueError, match="command is required"):
            await handle_mcp_add_server(
                runtime, {"name": "x", "type": "local"}, transport, 1, "c1",
            )

    @pytest.mark.anyio
    async def test_requires_url_for_remote(self, runtime, transport):
        with pytest.raises(ValueError, match="url is required"):
            await handle_mcp_add_server(
                runtime, {"name": "x", "type": "remote"}, transport, 1, "c1",
            )

    @pytest.mark.anyio
    async def test_invalid_type(self, runtime, transport):
        with pytest.raises(ValueError, match="Invalid MCP server type"):
            await handle_mcp_add_server(
                runtime, {"name": "x", "type": "invalid"}, transport, 1, "c1",
            )

    @pytest.mark.anyio
    async def test_connection_failure(self, runtime, transport):
        runtime.add_mcp_server = AsyncMock(side_effect=RuntimeError("connection failed"))
        with pytest.raises(ValueError, match="Failed to connect"):
            await handle_mcp_add_server(
                runtime,
                {"name": "bad-server", "type": "local", "command": ["bad"]},
                transport, 1, "c1",
            )


class TestHandleMCPRemoveServer:
    @pytest.mark.anyio
    async def test_removes_server(self, runtime, transport):
        runtime.remove_mcp_server = AsyncMock(return_value=3)
        result = await handle_mcp_remove_server(
            runtime, {"name": "test-server"}, transport, 1, "c1",
        )
        assert result["status"] == "disconnected"
        assert result["name"] == "test-server"
        assert result["unregistered_tools"] == 3

    @pytest.mark.anyio
    async def test_requires_name(self, runtime, transport):
        with pytest.raises(ValueError, match="name is required"):
            await handle_mcp_remove_server(runtime, {}, transport, 1, "c1")


class TestHandleWorkspaceSet:
    @pytest.mark.anyio
    async def test_updates_workspace_and_sessions(self, runtime, transport, tmp_path):
        resolved = str(tmp_path)
        result = await handle_workspace_set(
            runtime, {"workspace": resolved}, transport, 1, "c1"
        )
        assert result["workspace"] == resolved
        assert runtime.tool_registry.workspace == resolved
        runtime.update_sessions_workspace_env.assert_called_once_with(resolved)

    @pytest.mark.anyio
    async def test_requires_workspace(self, runtime, transport):
        result = await handle_workspace_set(
            runtime, {"workspace": ""}, transport, 1, "c1"
        )
        assert "error" in result

    @pytest.mark.anyio
    async def test_requires_existing_directory(self, runtime, transport):
        result = await handle_workspace_set(
            runtime, {"workspace": "/nonexistent/path"}, transport, 1, "c1"
        )
        assert "error" in result


def _async_gen(items):
    async def gen():
        for item in items:
            yield item

    return gen()
