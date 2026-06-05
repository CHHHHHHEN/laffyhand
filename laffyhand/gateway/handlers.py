from __future__ import annotations

import asyncio
import itertools
import os
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from laffyhand.agent.llm.specs.models import AssistantMessage, Message, SystemMessage, ToolMessage, UserMessage
from laffyhand.agent.schemas import TextDelta, StepFinish, Finish, PermissionRequest
from laffyhand.agent.tools.permission import request_callback as _pm_callback
from laffyhand.agent.schemas import (
    AgentState,
    SessionID,
    SessionUsage,
)
from laffyhand.gateway.protocol import (
    AGENT_LIST,
    INITIALIZE,
    SHUTDOWN,
    SESSION_CREATE,
    SESSION_LIST,
    SESSION_LOAD,
    SESSION_DELETE,
    SESSION_FORK,
    SESSION_SEARCH,
    SESSION_SET_TITLE,
    TOOLS_SET_DISABLED,
    MCP_ADD_SERVER,
    MCP_REMOVE_SERVER,
    SESSION_GENERATE_TITLE,
    SESSION_ARCHIVE,
    SUBAGENT_LIST_ACTIVE,
    USAGE_GET,
    CHAT,
    CHAT_STREAM,
    CHAT_CANCEL,
    CHAT_STEER,
    TOOLS_LIST,
    CONFIG_PROVIDERS,
    MCP_STATUS,
    SESSION_SET_CONFIG,
    WORKSPACE_SET,
    PERMISSION_RESPOND,
    TODO_LIST,
    TODO_UPDATE,
    SESSION_COMPACT,
    Notification,
)

if TYPE_CHECKING:
    from laffyhand.agent.runtime import AgentRuntime
    from laffyhand.gateway.dispatcher import Dispatcher
    from laffyhand.gateway.transport import Transport


_MESSAGE_COUNTER = itertools.count(1)


def _next_msg_id() -> str:
    return f"msg-{int(time.time() * 1000)}-{next(_MESSAGE_COUNTER)}"


def _serialize_messages(messages: list[Message]) -> list[dict[str, Any]]:
    # First pass: collect ToolMessage results keyed by tool_call_id
    tool_results: dict[str, tuple[str, bool]] = {}
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_results[msg.tool_call_id] = (msg.content, msg.is_error)

    result: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            result.append(
                {
                    "id": _next_msg_id(),
                    "role": "system",
                    "content": msg.content,
                    "createdAt": int(time.time() * 1000),
                }
            )
        elif isinstance(msg, UserMessage):
            result.append(
                {
                    "id": _next_msg_id(),
                    "role": "user",
                    "content": msg.content,
                    "createdAt": int(time.time() * 1000),
                }
            )
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
                entry["toolCalls"] = []
                for tc in msg.tool_calls:
                    result_content, is_error = tool_results.get(
                        tc.tool_call_id, (None, False)
                    )
                    tool_entry: dict[str, Any] = {
                        "id": tc.tool_call_id,
                        "name": tc.tool_name,
                        "arguments": tc.args,
                    }
                    if result_content is not None:
                        tool_entry["status"] = "error" if is_error else "completed"
                        tool_entry["result"] = result_content
                        tool_entry["isError"] = is_error
                    else:
                        tool_entry["status"] = "pending"
                    entry["toolCalls"].append(tool_entry)
            if msg.tokens:
                usage = {
                    "inputTokens": msg.tokens.input_tokens,
                    "outputTokens": msg.tokens.output_tokens,
                }
                if msg.tokens.reasoning_tokens is not None:
                    usage["reasoningTokens"] = msg.tokens.reasoning_tokens
                entry["usage"] = usage
            result.append(entry)
        elif isinstance(msg, ToolMessage):
            # Skip — content is embedded in the corresponding AssistantMessage toolCalls
            pass
    return result


async def _system_prompt(runtime: AgentRuntime, base: str = "", agent_name: str = "") -> str:
    if not base:
        name = agent_name or "build"
        agent = runtime.agent_registry.get(name)
        base = agent.system_prompt if agent and agent.system_prompt else "You are a helpful assistant."
    return await runtime.build_system_prompt(base)


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
        "session_id": None,
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
    session_id = await _ensure_session(runtime, params)
    state = runtime.get_state(session_id)
    if state is None:
        raise RuntimeError("Session creation failed")
    return {"session_id": state.session_id}


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
                "agent": s.agent_version,
                "provider": s.provider,
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
    state = runtime.load_session_state(session_id)
    if state is None:
        raise ValueError(f"Session not found: {session_id}")
    session = runtime.session_manager.get(session_id)
    is_streaming = False
    if transport.dispatcher is not None:
        is_streaming = transport.dispatcher.get_active_session_stream(session_id) is not None
    return {
        "session_id": state.session_id,
        "title": session.title if session else None,
        "model": session.model if session else "",
        "agent": session.agent_version if session else "",
        "messages_count": len(state.messages),
        "turn_count": state.turn_count,
        "usage": state.usage.model_dump() if state.usage else None,
        "messages": _serialize_messages(state.messages),
        "is_streaming": is_streaming,
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
    session_id = params.get("session_id", "")
    if not session_id:
        raise ValueError("session_id is required")
    child_id = runtime.fork_session(session_id)
    if child_id is None:
        raise ValueError(f"Session not found: {session_id}")
    return {"session_id": child_id}


async def _prepare_chat(
    runtime: AgentRuntime,
    params: dict[str, Any],
) -> str:
    message: str = params.get("message", "")
    if not message:
        raise ValueError("message is required")

    session_id: str | None = params.get("session_id")
    if not session_id:
        session_id = await _ensure_session(runtime, params)

    if session_id is None:
        raise RuntimeError("Session ID is None after preparation")
    state = runtime.get_state(session_id)
    if state is None:
        raise RuntimeError(f"Session state not found: {session_id}")
    state.step = 0
    user_message = UserMessage(content=message)
    async with runtime.get_session_lock(session_id):
        state.messages.append(user_message)

    # If this is the first time this session is persisted to DB,
    # include the SystemMessage (at state.messages[0]) so that
    # len(state.messages) stays in sync with the DB count.
    # This prevents save_state() from re-storing the last message
    # on shutdown (which would cause a duplicate after restart).
    existing_session = runtime.session_manager.get(session_id)
    if existing_session is None and len(state.messages) >= 2 and isinstance(state.messages[0], SystemMessage):
        runtime.session_manager.store_messages(session_id, [state.messages[0], user_message])
    else:
        runtime.session_manager.store_messages(session_id, [user_message])
    return session_id


async def handle_chat(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id = await _prepare_chat(runtime, params)

    content_parts: list[str] = []
    finish_reason = ""
    usage_info = None
    logger.debug(f"Chat started (id={request_id}, conn={conn_id})")

    async with runtime.get_session_lock(session_id):
        async for event in runtime.run_agent_turn(session_id=session_id):
            if isinstance(event, TextDelta):
                content_parts.append(event.text)
            elif isinstance(event, StepFinish):
                finish_reason = event.reason
                usage_info = event.usage

    last_content = "".join(content_parts)
    logger.debug(
        f"Chat finished (id={request_id}, conn={conn_id}, finish={finish_reason})"
    )
    await runtime._generate_title(session_id, "auto")
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

    async def _permission_callback(permission: str, pattern: str) -> tuple[bool, str | None]:
        request_id = str(uuid.uuid4())
        event = asyncio.Event()
        runtime.pending_permissions[request_id] = (event, permission, pattern, None, None)
        try:
            pr = PermissionRequest(
                request_id=request_id, permission=permission, pattern=pattern
            )
            notif = Notification(method="event", params=pr.model_dump())
            await transport.send(notif.json())
            try:
                await asyncio.wait_for(event.wait(), timeout=300.0)
            except asyncio.TimeoutError:
                logger.warning(f"Permission request {request_id} timed out")
                return (False, None)
            _, _, _, result, reason = runtime.pending_permissions.get(
                request_id, (None, None, None, False, None)
            )
            return (bool(result), reason)
        finally:
            runtime.pending_permissions.pop(request_id, None)

    async def _event_sink(event: Any) -> None:
        notif = Notification(method="event", params=event.model_dump(exclude_none=True))
        await transport.send(notif.json())

    token = _pm_callback.set(_permission_callback)

    try:
        async with runtime.get_session_lock(session_id):
            cancelled = False
            try:
                async for event in runtime.run_agent_turn(
                    session_id=session_id,
                    event_sink=_event_sink,
                ):
                    # Drain background subagent events
                    if runtime.subagent_manager:
                        bg_events = await runtime.subagent_manager.drain_events(
                            session_id
                        )
                        for bg_event in bg_events:
                            await _event_sink(bg_event)

                    notif = Notification(
                        method="event",
                        params=event.model_dump(exclude_none=True),
                    )
                    await transport.send(notif.json())
                    if isinstance(event, StepFinish):
                        finish_reason = event.reason
                        usage_info = event.usage
            except asyncio.CancelledError:
                cancelled = True
                finish_reason = "cancelled"
                logger.info(
                    f"Chat stream cancelled for session {session_id} (conn={conn_id})"
                )
            except Exception:
                logger.exception(
                    f"Chat stream error for session {session_id} (conn={conn_id})"
                )
                err_notif = Notification(
                    method="event",
                    params={
                        "type": "error",
                        "data": "Internal error during streaming",
                    },
                )
                try:
                    await transport.send(err_notif.json())
                except Exception:
                    logger.warning(
                        "Failed to send error event to client in chat stream"
                    )
            finally:
                # Drain background subagent events (also on cancel/error)
                if runtime.subagent_manager:
                    bg_events = await runtime.subagent_manager.drain_events(session_id)
                    for bg_event in bg_events:
                        try:
                            await _event_sink(bg_event)
                        except Exception:
                            logger.warning("Failed to relay background event")

                if cancelled:
                    cancel_notif = Notification(
                        method="event",
                        params={
                            "type": "cancelled",
                            "data": "Stream cancelled",
                        },
                    )
                    await transport.send(cancel_notif.json())

        # Generate title synchronously before finish event
        state = runtime.get_state(session_id)
        actual_sid = state.session_id if (state and state.session_id) else session_id
        await runtime._generate_title(actual_sid, "auto")

        # Unregister session from stream registry BEFORE sending finish event,
        # so the frontend can immediately send a new message without hitting
        # SESSION_ALREADY_STREAMING (HTTP 409).
        session_dispatcher = getattr(transport, "dispatcher", None)
        if session_dispatcher is not None:
            session_dispatcher.unregister_session_stream(session_id)

        # Check for leftover steer that wasn't consumed by tool batch
        leftover_steer: str | None = None
        state = runtime.get_state(session_id)
        if state is not None:
            async with runtime.get_session_lock(session_id):
                if state.pending_steer:
                    leftover_steer = state.pending_steer
                    state.pending_steer = None

        done_params = Finish(
            reason=finish_reason,
            usage=usage_info,
            session_id=session_id,
            session_usage=state.usage.model_dump() if state and state.usage else None,
            leftover_steer=leftover_steer,
        ).model_dump(exclude_none=True)
        done = Notification(method="event", params=done_params)
        try:
            await transport.send(done.json())
        except Exception:
            logger.warning(
                "Failed to send finish event to client (connection may be closed)"
            )
    finally:
        _pm_callback.reset(token)


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
        raise ValueError("session_id is required")
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
    session_id: str | None = params.get("session_id")
    if session_id:
        runtime.interrupt_session(session_id)

    dispatcher: Dispatcher | None = getattr(transport, "dispatcher", None)

    # 1. Session-scoped cancel (precise — only cancels one session's stream)
    if dispatcher is not None and session_id:
        if await dispatcher.cancel_session_stream(session_id):
            logger.info(f"Streaming task cancelled for session {session_id}")
            return {"status": "cancelled"}

    # 2. Conn_id-based cancel via dispatcher (WS/stdio transports)
    if dispatcher is not None:
        if dispatcher.cancel_connection(conn_id):
            logger.info(f"Streaming task cancelled for connection {conn_id}")
            return {"status": "cancelled"}
        logger.debug(f"No active streaming task for connection {conn_id}")

    # 3. HTTP SSE canceller fallback
    sse_canceller = getattr(transport, "sse_canceller", None)
    if sse_canceller is not None:
        if sse_canceller(conn_id):
            logger.info(f"SSE stream cancelled for connection {conn_id}")
            return {"status": "cancelled"}
        logger.debug(f"No active SSE stream for connection {conn_id}")

    # 4. No cancellation mechanism available
    if dispatcher is None and sse_canceller is None:
        logger.warning(
            f"Cancellation not supported for transport {type(transport).__name__} (conn={conn_id})"
        )

    return {"status": "no_active_stream"}


async def handle_tools_list(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    tools = await runtime.tool_registry.build_tool_definitions()
    session_id: str | None = params.get("session_id")
    state = runtime.get_state(session_id) if session_id else None
    disabled = state.disabled_tools if state else set()
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "enabled": t.name not in disabled,
            }
            for t in tools
        ],
    }


async def handle_tools_set_disabled(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    tool_names: list[str] = params.get("tool_names", [])
    session_id: str | None = params.get("session_id")
    if not session_id:
        raise ValueError("session_id is required")
    state = runtime.get_state(session_id)
    if state is None:
        raise RuntimeError(f"Session not found: {session_id}")
    state.disabled_tools = set(tool_names)
    return {"status": "ok", "disabled_tools": tool_names}


async def _ensure_session(
    runtime: AgentRuntime,
    params: dict[str, Any],
) -> str:
    agent_name = params.get("agent", "") or "build"
    system_content = await _system_prompt(runtime, params.get("system_prompt", ""), agent_name)
    system_message = SystemMessage(content=system_content)
    # Create session in memory only — defer DB persistence until the first message is stored
    from laffyhand.agent.session.models import Session as SessionModel
    session = SessionModel(
        title=params.get("title", ""),
        cwd=params.get("cwd", os.getcwd()),
        provider=params.get("provider", ""),
        model=params.get("model", ""),
        agent_version=agent_name,
    )
    runtime.session_manager.set_pending_meta(
        session.id,
        title=session.title,
        cwd=session.cwd,
        provider=str(session.provider) if session.provider else "",
        model=str(session.model) if session.model else "",
        agent_version=session.agent_version,
    )
    state = AgentState(
        messages=[system_message],
        session_id=SessionID(session.id),
        usage=SessionUsage(context_size=runtime.context_size),
    )
    runtime._states[session.id] = state
    runtime._schedule_title_generation(session.id, "on_create")
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
                "agent": s.agent_version,
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
    session_id: str | None = params.get("session_id")
    if not session_id:
        raise ValueError("session_id is required")
    runtime.session_manager.set_title(session_id, title)
    return {"status": "ok", "session_id": session_id, "title": title}


async def handle_session_generate_title(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str | None = params.get("session_id")
    if not session_id:
        raise ValueError("session_id is required")
    title = await runtime._do_generate_title(session_id)
    return {"title": title}


async def handle_session_archive(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str | None = params.get("session_id")
    if not session_id:
        raise ValueError("session_id is required")
    runtime.session_manager.archive(session_id)
    return {"status": "archived", "session_id": session_id}


async def handle_subagent_list_active(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str | None = params.get("session_id")
    if not session_id:
        return {"subagents": []}
    return {"subagents": runtime.subagent_manager.list_active(session_id)}


async def handle_config_providers(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    providers = {}
    for key, pc in runtime.config.llm.providers.items():
        providers[key] = {
            "type": pc.type,
            "base_url": pc.base_url,
            "models": [
                {"name": m.name, "context_size": m.context_size} for m in pc.models
            ],
        }
    logger.debug(
        f"config/providers: returning {len(providers)} provider(s) (conn={conn_id})"
    )
    return {
        "default_provider": runtime.config.llm.default_provider,
        "providers": providers,
    }


async def handle_mcp_status(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    status = runtime.mcp_service.get_status()
    logger.debug(f"mcp/status: returning {len(status)} server(s) (conn={conn_id})")
    return {
        "servers": [{"name": name, "status": st} for name, st in status.items()],
    }


async def handle_mcp_add_server(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    name: str = params.get("name", "")
    if not name:
        raise ValueError("name is required")
    from laffyhand.agent.mcp.config import LocalMCPConfig, RemoteMCPConfig
    from laffyhand.agent.mcp.config import MCPConfig as MCPCfg
    server_type: str = params.get("type", "local")
    if server_type == "local":
        command: list[str] = params.get("command", [])
        if not command:
            raise ValueError("command is required for local MCP servers")
        cfg: MCPCfg = LocalMCPConfig(command=command, env=params.get("env", {}), timeout=params.get("timeout", 300))
    elif server_type == "remote":
        url: str = params.get("url", "")
        if not url:
            raise ValueError("url is required for remote MCP servers")
        cfg = RemoteMCPConfig(url=url, transport=params.get("transport"), headers=params.get("headers", {}), timeout=params.get("timeout", 300))
    else:
        raise ValueError(f"Invalid MCP server type: {server_type}")
    try:
        tool_names = await runtime.add_mcp_server(name, cfg)
        return {"status": "connected", "name": name, "tools": tool_names}
    except Exception as e:
        logger.error(f"Failed to add MCP server '{name}': {e}")
        raise ValueError(f"Failed to connect MCP server: {e}")


async def handle_mcp_remove_server(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    name: str = params.get("name", "")
    if not name:
        raise ValueError("name is required")
    count = await runtime.remove_mcp_server(name)
    return {"status": "disconnected", "name": name, "unregistered_tools": count}


async def handle_workspace_set(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    workspace: str = params.get("workspace", "")
    if not workspace:
        return {"error": "workspace path is required"}
    resolved = str(Path(workspace).resolve())
    if not os.path.isdir(resolved):
        return {"error": f"workspace path does not exist: {workspace}"}
    runtime.tool_registry.workspace = resolved
    logger.info(f"Workspace set to {resolved} (conn={conn_id})")
    return {"workspace": resolved}


async def handle_session_set_config(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    provider = params.get("provider", "")
    model = params.get("model", "")
    session_id: str | None = params.get("session_id")
    if not session_id:
        raise ValueError("session_id is required")
    state = runtime.get_state(session_id)
    if state is None:
        raise RuntimeError(f"Session not found: {session_id}")
    runtime.session_manager.complete(session_id)
    new_session_id = runtime.session_manager.create(
        provider=provider,
        model=model,
    ).id
    state.session_id = SessionID(new_session_id)
    runtime._states[new_session_id] = state
    runtime._states.pop(session_id, None)
    return {"session_id": new_session_id}


async def handle_permission_respond(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    req_id: str = params.get("request_id", "")
    if req_id not in runtime.pending_permissions:
        raise ValueError(f"Unknown or expired permission request: {req_id}")
    action: str = params.get("action", "")
    if action not in ("allow", "always", "deny"):
        raise ValueError(f"Invalid permission action: {action}")
    reason: str | None = params.get("reason")
    event, permission, pattern, _, _ = runtime.pending_permissions[req_id]
    if action == "always":
        runtime.tool_registry.permission.add_rule(f"{permission}:{pattern}", "allow")
        result = True
    elif action == "allow":
        result = True
    else:
        result = False
    runtime.pending_permissions[req_id] = (event, permission, pattern, result, reason)
    event.set()
    logger.info(
        f"Permission '{permission}:{pattern}' resolved: {action} (conn={conn_id})"
    )
    return {"status": "ok"}


async def handle_usage_get(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str | None = params.get("session_id")
    if not session_id:
        return {
            "curr_context_usage": 0,
            "total_input": 0,
            "total_output": 0,
            "total_reasoning": 0,
            "context_size": 0,
        }
    state = runtime.get_state(session_id)
    if state is None or state.usage is None:
        return {
            "curr_context_usage": 0,
            "total_input": 0,
            "total_output": 0,
            "total_reasoning": 0,
            "context_size": 0,
        }
    return {
        "curr_context_usage": state.usage.curr_context_usage,
        "total_input": state.usage.total_input,
        "total_output": state.usage.total_output,
        "total_reasoning": state.usage.total_reasoning,
        "context_size": state.usage.context_size,
    }


async def handle_todo_list(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str = params.get("session_id", "")
    if not session_id:
        return {"tasks": []}
    status = params.get("status")
    tasks = runtime.todo_manager.get_tasks(session_id, status=status)
    return {
        "tasks": [
            {
                "id": t.id,
                "sessionId": t.session_id,
                "content": t.content,
                "status": t.status,
                "priority": t.priority,
                "dependsOn": t.depends_on,
                "createdAt": t.created_at.isoformat(),
                "updatedAt": t.updated_at.isoformat(),
                "completedAt": t.completed_at.isoformat() if t.completed_at else None,
                "taskToolId": t.task_tool_id,
                "blockedBy": t.metadata.get("blocked_by", []),
            }
            for t in tasks
        ],
    }


async def handle_todo_update(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str = params.get("session_id", "")
    if not session_id:
        raise ValueError("session_id is required")
    task_id: str = params.get("task_id", "")
    if not task_id:
        raise ValueError("task_id is required")

    from laffyhand.agent.session.todo import TodoUpdate as TodoUpdateModel

    updates = TodoUpdateModel(
        status=params.get("status"),
        priority=params.get("priority"),
        content=params.get("content"),
    )
    item = runtime.todo_manager.update_task(task_id, session_id, updates)
    if item is None:
        raise ValueError(f"Task not found: {task_id}")
    return {
        "id": item.id,
        "sessionId": item.session_id,
        "content": item.content,
        "status": item.status,
        "priority": item.priority,
        "dependsOn": item.depends_on,
        "createdAt": item.created_at.isoformat(),
        "updatedAt": item.updated_at.isoformat(),
        "completedAt": item.completed_at.isoformat() if item.completed_at else None,
        "taskToolId": item.task_tool_id,
        "blockedBy": item.metadata.get("blocked_by", []),
    }


async def handle_agent_list(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    agents = runtime.agent_registry.list_visible()
    return {
        "agents": [
            {
                "name": a.name,
                "description": a.description,
                "mode": a.mode,
                "system_prompt": a.system_prompt,
                "model": a.model,
            }
            for a in agents
        ],
    }


async def handle_session_compact(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str = params.get("session_id", "")
    if not session_id:
        raise ValueError("session_id is required")
    new_id = await runtime.compact_session(session_id)
    if new_id is None:
        return {
            "status": "nothing_to_compact",
            "session_id": session_id,
            "parent_id": None,
        }
    return {
        "status": "compacted",
        "session_id": new_id,
        "parent_id": session_id,
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
    dispatcher.register(AGENT_LIST, handle_agent_list)
    dispatcher.register(SUBAGENT_LIST_ACTIVE, handle_subagent_list_active)
    dispatcher.register(USAGE_GET, handle_usage_get)
    dispatcher.register(CONFIG_PROVIDERS, handle_config_providers)
    dispatcher.register(MCP_STATUS, handle_mcp_status)
    dispatcher.register(MCP_ADD_SERVER, handle_mcp_add_server)
    dispatcher.register(MCP_REMOVE_SERVER, handle_mcp_remove_server)
    dispatcher.register(SESSION_SET_CONFIG, handle_session_set_config)
    dispatcher.register(WORKSPACE_SET, handle_workspace_set)
    dispatcher.register(CHAT, handle_chat)
    dispatcher.register(CHAT_STREAM, handle_chat_stream, streaming=True)
    dispatcher.register(CHAT_CANCEL, handle_chat_cancel)
    dispatcher.register(CHAT_STEER, handle_chat_steer)
    dispatcher.register(TOOLS_LIST, handle_tools_list)
    dispatcher.register(TOOLS_SET_DISABLED, handle_tools_set_disabled)
    dispatcher.register(PERMISSION_RESPOND, handle_permission_respond)
    dispatcher.register(TODO_LIST, handle_todo_list)
    dispatcher.register(TODO_UPDATE, handle_todo_update)
    dispatcher.register(SESSION_COMPACT, handle_session_compact)
