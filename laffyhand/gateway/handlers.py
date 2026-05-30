from __future__ import annotations

import asyncio
import itertools
import os
import time
from typing import TYPE_CHECKING, Any

from loguru import logger

from laffyhand.agent.schemas import (
    SystemMessage, UserMessage, AssistantMessage, ToolMessage,
    AgentState, SessionUsage,
)
from laffyhand.gateway.protocol import (
    INITIALIZE, SHUTDOWN, SESSION_CREATE, SESSION_LIST, SESSION_LOAD,
    SESSION_DELETE, SESSION_FORK, SESSION_SEARCH, SESSION_SET_TITLE,
    SESSION_GENERATE_TITLE, SESSION_ARCHIVE, SUBAGENT_LIST_ACTIVE,
    USAGE_GET, CHAT, CHAT_STREAM, CHAT_CANCEL, CHAT_STEER, TOOLS_LIST, Notification,
)

if TYPE_CHECKING:
    from laffyhand.agent.runtime import AgentRuntime
    from laffyhand.gateway.dispatcher import Dispatcher
    from laffyhand.gateway.transport import Transport


_MESSAGE_COUNTER = itertools.count(1)


def _next_msg_id() -> str:
    return f"msg-{int(time.time() * 1000)}-{next(_MESSAGE_COUNTER)}"


def _serialize_messages(messages: list) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            result.append({
                "id": _next_msg_id(),
                "role": "system",
                "content": msg.content,
                "createdAt": int(time.time() * 1000),
            })
        elif isinstance(msg, UserMessage):
            result.append({
                "id": _next_msg_id(),
                "role": "user",
                "content": msg.content,
                "createdAt": int(time.time() * 1000),
            })
        elif isinstance(msg, AssistantMessage):
            entry: dict[str, Any] = {
                "id": _next_msg_id(),
                "role": "assistant",
                "content": msg.content or "",
                "createdAt": int(time.time() * 1000),
            }
            if msg.reasoning:
                entry["reasoning"] = msg.reasoning
            if msg.tool_calls:
                entry["toolCalls"] = [
                    {"id": tc.tool_call_id, "name": tc.tool_name, "arguments": tc.args}
                    for tc in msg.tool_calls
                ]
            if msg.tokens:
                entry["usage"] = {
                    "inputTokens": msg.tokens.input_tokens,
                    "outputTokens": msg.tokens.output_tokens,
                }
            result.append(entry)
        elif isinstance(msg, ToolMessage):
            result.append({
                "id": _next_msg_id(),
                "role": "tool",
                "content": msg.content,
                "tool_call_id": msg.tool_call_id,
                "createdAt": int(time.time() * 1000),
            })
    return result


def _system_prompt(runtime: AgentRuntime, base: str = "") -> str:
    return runtime.build_system_prompt(base or "You are a helpful assistant.")


async def handle_initialize(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    return {
        "protocol_version": "2.0",
        "server_info": {
            "name": "laffyhand",
            "version": "0.1.0",
        },
        "session_id": runtime.current_session_id,
    }


async def handle_shutdown(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> None:
    await runtime.shutdown()


async def handle_session_create(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    await _ensure_session(runtime, params)
    if runtime.state is None:
        raise RuntimeError("Session creation failed")
    return {"session_id": runtime.state.session_id}


async def handle_session_list(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    sessions = runtime.session_manager.list_sessions(
        status=params.get("status"),
        limit=params.get("limit", 20),
        offset=params.get("offset", 0),
    )
    return {
        "sessions": [
            {
                "id": s.id,
                "status": s.status,
                "title": s.title,
                "model": s.model,
                "message_count": s.message_count,
                "turn_count": s.turn_count,
                "input_tokens": s.input_tokens,
                "output_tokens": s.output_tokens,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ],
    }


async def handle_session_load(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str = params.get("session_id", "")
    if not session_id:
        raise ValueError("session_id is required")
    ok = runtime.switch_session(session_id)
    if not ok:
        raise ValueError(f"Session not found: {session_id}")
    if runtime.state is None:
        raise RuntimeError("Session load failed")
    session = runtime.session_manager.get(session_id)
    return {
        "session_id": runtime.state.session_id,
        "model": session.model if session else "",
        "messages_count": len(runtime.state.messages),
        "turn_count": runtime.state.turn_count,
        "usage": runtime.state.usage.model_dump() if runtime.state.usage else None,
        "messages": _serialize_messages(runtime.state.messages),
    }


async def handle_session_delete(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str = params.get("session_id", "")
    if not session_id:
        raise ValueError("session_id is required")
    runtime.session_manager.delete(session_id)
    _session_locks.pop(session_id, None)
    return {"status": "deleted", "session_id": session_id}


async def handle_session_fork(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    child_id = runtime.fork_session()
    if child_id is None:
        raise ValueError("No active session to fork")
    return {"session_id": child_id}


_session_locks: dict[str, asyncio.Lock] = {}


def _get_session_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _session_locks:
        _session_locks[session_id] = asyncio.Lock()
    return _session_locks[session_id]


async def _prepare_chat(
    runtime: AgentRuntime,
    params: dict[str, Any],
) -> str:
    message: str = params.get("message", "")
    if not message:
        raise ValueError("message is required")

    session_id: str | None = params.get("session_id")
    if session_id:
        if not runtime.switch_session(session_id):
            raise ValueError(f"Session not found: {session_id}")
    elif runtime.state is None:
        session_id = await _ensure_session(runtime, params)
    else:
        session_id = runtime.current_session_id

    if session_id is None:
        raise RuntimeError("Session ID is None after preparation")
    state = runtime.get_state(session_id)
    if state is None:
        raise RuntimeError(f"Session state not found: {session_id}")
    state.step = 0
    user_message = UserMessage(content=message)
    async with _get_session_lock(session_id):
        state.messages.append(user_message)
    return session_id


async def handle_chat(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id = await _prepare_chat(runtime, params)

    last_content = ""
    finish_reason = ""
    usage_info = None
    logger.debug(f"Chat started (id={request_id}, conn={conn_id})")

    async for event in runtime.run_agent_turn(session_id=session_id):
        if event.type == "content" and event.data:
            last_content += event.data
        if event.finish_reason:
            finish_reason = event.finish_reason
        if event.usage:
            usage_info = event.usage

    logger.debug(f"Chat finished (id={request_id}, conn={conn_id}, finish={finish_reason})")
    return {
        "content": last_content,
        "finish_reason": finish_reason,
        "usage": usage_info.model_dump() if usage_info else None,
        "session_id": session_id,
    }


async def handle_chat_stream(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> None:
    session_id = await _prepare_chat(runtime, params)

    finish_reason = ""
    usage_info = None
    last_content = ""

    try:
        async for event in runtime.run_agent_turn(session_id=session_id):
            notif = Notification(
                method="event",
                params={
                    "type": event.type,
                    "data": event.data,
                    "finish_reason": event.finish_reason,
                    "usage": event.usage.model_dump() if event.usage else None,
                },
            )
            await transport.send(notif.json())
            if event.finish_reason:
                finish_reason = event.finish_reason
            if event.usage:
                usage_info = event.usage
            if event.type == "content" and event.data:
                last_content += event.data
    except asyncio.CancelledError:
        finish_reason = "cancelled"
        logger.info(f"Chat stream cancelled for session {session_id} (conn={conn_id})")
    except Exception:
        logger.exception(f"Chat stream error for session {session_id} (conn={conn_id})")
        try:
            err_notif = Notification(
                method="event",
                params={
                    "type": "error",
                    "data": "Internal error during streaming",
                },
            )
            await transport.send(err_notif.json())
        except Exception:
            logger.warning("Failed to send error event to client in chat stream")

    # Check for leftover steer that wasn't consumed by tool batch
    leftover_steer: str | None = None
    state = runtime.get_state(session_id)
    if state is not None:
        async with _get_session_lock(session_id):
            if state.pending_steer:
                leftover_steer = state.pending_steer
                state.pending_steer = None

    done = Notification(
        method="event",
        params={
            "type": "finish",
            "data": last_content,
            "finish_reason": finish_reason,
            "usage": usage_info.model_dump() if usage_info else None,
            "session_id": session_id,
            "session_usage": runtime.state.usage.model_dump() if runtime.state else None,
            "leftover_steer": leftover_steer,
        },
    )
    try:
        await transport.send(done.json())
    except Exception:
        logger.warning("Failed to send finish event to client (connection may be closed)")


async def handle_chat_steer(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    message: str = params.get("message", "")
    if not message:
        raise ValueError("message is required")

    session_id: str | None = params.get("session_id")
    if not session_id:
        session_id = runtime.current_session_id

    if session_id is None:
        raise RuntimeError("No active session to steer")
    ok = runtime.steer_session(session_id, message)
    if not ok:
        raise RuntimeError(f"Session state not found: {session_id}")
    return {"status": "steered", "session_id": session_id}


async def handle_chat_cancel(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    # 0. Signal interrupt to the agent state if we can identify the session
    session_id: str | None = params.get("session_id")
    if session_id:
        runtime.interrupt_session(session_id)
    else:
        current = runtime.current_session_id
        if current:
            runtime.interrupt_session(current)

    # 1. Try dispatcher-based cancellation (WS/stdio transports)
    dispatcher: Dispatcher | None = getattr(transport, "_dispatcher", None)
    if dispatcher is not None:
        if dispatcher.cancel_connection(conn_id):
            logger.info(f"Streaming task cancelled for connection {conn_id}")
            return {"status": "cancelled"}
        logger.debug(f"No active streaming task for connection {conn_id}")
        return {"status": "no_active_stream"}

    # 2. Try HTTP SSE transport cancellation
    sse_canceller = getattr(transport, "_sse_canceller", None)
    if sse_canceller is not None:
        if sse_canceller(conn_id):
            logger.info(f"SSE stream cancelled for connection {conn_id}")
            return {"status": "cancelled"}
        logger.debug(f"No active SSE stream for connection {conn_id}")
        return {"status": "no_active_stream"}

    # 3. No cancellation mechanism available
    logger.warning(f"Cancellation not supported for transport {type(transport).__name__} (conn={conn_id})")
    return {"status": "cancellation_not_supported"}


async def handle_tools_list(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    tools = await runtime.tool_registry.build_tool_definitions()
    return {
        "tools": [t.model_dump() for t in tools],
    }


async def _ensure_session(
    runtime: AgentRuntime,
    params: dict[str, Any],
) -> str:
    system_content = _system_prompt(runtime, params.get("system_prompt", ""))
    system_message = SystemMessage(content=system_content)
    session = runtime.session_manager.create(
        title=params.get("title", ""),
        cwd=params.get("cwd", os.getcwd()),
        model=params.get("model", ""),
    )
    runtime.state = AgentState(
        messages=[system_message],
        session_id=session.id,
        usage=SessionUsage(context_size=runtime.context_size),
    )
    return session.id


async def handle_session_search(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    query: str = params.get("query", "")
    if not query:
        raise ValueError("query is required")
    limit = params.get("limit", 20)
    sessions = runtime.session_manager.search(query, limit=limit)
    return {
        "sessions": [
            {
                "id": s.id,
                "status": s.status,
                "title": s.title,
                "message_count": s.message_count,
                "turn_count": s.turn_count,
                "input_tokens": s.input_tokens,
                "output_tokens": s.output_tokens,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ],
    }


async def handle_session_set_title(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    title: str = params.get("title", "")
    if not title:
        raise ValueError("title is required")
    session_id: str | None = params.get("session_id") or runtime.current_session_id
    if not session_id:
        raise ValueError("No active session")
    runtime.session_manager.set_title(session_id, title)
    return {"status": "ok", "session_id": session_id, "title": title}


async def handle_session_generate_title(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    title = await runtime.generate_title_for_current()
    return {"title": title}


async def handle_session_archive(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str | None = params.get("session_id") or runtime.current_session_id
    if not session_id:
        raise ValueError("No active session")
    runtime.session_manager.archive(session_id)
    _session_locks.pop(session_id, None)
    return {"status": "archived", "session_id": session_id}


async def handle_subagent_list_active(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str | None = params.get("session_id") or runtime.current_session_id
    if not session_id:
        return {"subagents": []}
    return {"subagents": runtime.subagent_manager.list_active(session_id)}


async def handle_usage_get(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    return {
        "total_input": runtime.state.usage.total_input if runtime.state else 0,
        "total_output": runtime.state.usage.total_output if runtime.state else 0,
        "total_reasoning": runtime.state.usage.total_reasoning if runtime.state else 0,
        "context_size": runtime.state.usage.context_size if runtime.state else 0,
    }


def register_all_handlers(dispatcher: Dispatcher) -> None:
    dispatcher.register(INITIALIZE, handle_initialize)
    dispatcher.register(SHUTDOWN, handle_shutdown)
    dispatcher.register(SESSION_CREATE, handle_session_create)
    dispatcher.register(SESSION_LIST, handle_session_list)
    dispatcher.register(SESSION_LOAD, handle_session_load)
    dispatcher.register(SESSION_DELETE, handle_session_delete)
    dispatcher.register(SESSION_FORK, handle_session_fork)
    dispatcher.register(SESSION_SEARCH, handle_session_search)
    dispatcher.register(SESSION_SET_TITLE, handle_session_set_title)
    dispatcher.register(SESSION_GENERATE_TITLE, handle_session_generate_title)
    dispatcher.register(SESSION_ARCHIVE, handle_session_archive)
    dispatcher.register(SUBAGENT_LIST_ACTIVE, handle_subagent_list_active)
    dispatcher.register(USAGE_GET, handle_usage_get)
    dispatcher.register(CHAT, handle_chat)
    dispatcher.register(CHAT_STREAM, handle_chat_stream, streaming=True)
    dispatcher.register(CHAT_CANCEL, handle_chat_cancel)
    dispatcher.register(CHAT_STEER, handle_chat_steer)
    dispatcher.register(TOOLS_LIST, handle_tools_list)
