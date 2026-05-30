from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from loguru import logger

from laffyhand.agent.schemas import (
    SystemMessage, UserMessage, AgentState, SessionUsage,
)

if TYPE_CHECKING:
    from laffyhand.agent.runtime import AgentRuntime
    from laffyhand.gateway.dispatcher import Dispatcher
    from laffyhand.gateway.transport import Transport


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
    assert runtime.state is not None
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
                "message_count": s.message_count,
                "turn_count": s.turn_count,
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
    assert runtime.state is not None
    return {
        "session_id": runtime.state.session_id,
        "messages_count": len(runtime.state.messages),
        "turn_count": runtime.state.turn_count,
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


async def handle_chat(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    message: str = params.get("message", "")
    if not message:
        raise ValueError("message is required")

    if runtime.state is None:
        await _ensure_session(runtime, params)

    assert runtime.state is not None
    runtime.state.step = 0
    user_message = UserMessage(content=message)
    runtime.state.messages.append(user_message)

    last_content = ""
    finish = ""
    usage_info = None
    logger.debug(f"Chat started (id={request_id}, conn={conn_id})")

    async for event in runtime.run_agent_turn():
        if event.type == "content" and event.data:
            last_content += event.data
        if event.finish_reason:
            finish = event.finish_reason
        if event.usage:
            usage_info = event.usage

    logger.debug(f"Chat finished (id={request_id}, conn={conn_id}, finish={finish})")
    return {
        "content": last_content,
        "finish_reason": finish,
        "usage": usage_info.model_dump() if usage_info else None,
        "session_id": runtime.state.session_id,
    }


async def handle_chat_stream(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> None:
    from laffyhand.gateway.protocol import Notification

    message: str = params.get("message", "")
    if not message:
        raise ValueError("message is required")

    if runtime.state is None:
        await _ensure_session(runtime, params)

    assert runtime.state is not None
    runtime.state.step = 0
    user_message = UserMessage(content=message)
    runtime.state.messages.append(user_message)

    finish = ""
    usage_info = None

    async for event in runtime.run_agent_turn():
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
            finish = event.finish_reason
        if event.usage:
            usage_info = event.usage

    done = Notification(
        method="event",
        params={
            "type": "finish",
            "data": "",
            "finish_reason": finish,
            "usage": usage_info.model_dump() if usage_info else None,
            "session_id": runtime.state.session_id,
        },
    )
    await transport.send(done.json())


async def handle_chat_cancel(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    logger.warning(f"Cancellation requested for connection {conn_id}, but streaming task cancellation is not yet implemented")
    return {"status": "cancelled"}


async def handle_tools_list(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    tools = runtime.tool_registry.build_tool_definitions()
    return {
        "tools": [t.model_dump() for t in tools],
    }


async def _ensure_session(
    runtime: AgentRuntime,
    params: dict[str, Any],
) -> None:
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
        usage=SessionUsage(context_size=runtime._context_size),
    )


def register_all_handlers(dispatcher: Dispatcher) -> None:
    """Register all RPC handlers on a dispatcher."""
    dispatcher.register("initialize", handle_initialize)
    dispatcher.register("shutdown", handle_shutdown)
    dispatcher.register("session/create", handle_session_create)
    dispatcher.register("session/list", handle_session_list)
    dispatcher.register("session/load", handle_session_load)
    dispatcher.register("session/delete", handle_session_delete)
    dispatcher.register("session/fork", handle_session_fork)
    dispatcher.register("chat", handle_chat)
    dispatcher.register("chat_stream", handle_chat_stream, streaming=True)
    dispatcher.register("chat/cancel", handle_chat_cancel)
    dispatcher.register("tools/list", handle_tools_list)
