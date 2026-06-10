from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any

from loguru import logger

from laffyhand.core.domain.messages import SystemMessage
from laffyhand.core.models import AgentState, SessionID, SessionUsage
from laffyhand.gateway.session_converters import _serialize_messages
from laffyhand.gateway.protocol import Notification

if TYPE_CHECKING:
    from laffyhand.core.runtime import AgentRuntime
    from laffyhand.gateway.transport import Transport


async def _system_prompt(runtime: AgentRuntime, base: str = "", agent_name: str = "") -> str:
    if not base:
        name = agent_name or "build"
        agent = runtime.agent_registry.get(name)
        base = agent.system_prompt if agent and agent.system_prompt else "You are a helpful assistant."
    return await runtime.build_system_prompt(base)


async def _ensure_session(
    runtime: AgentRuntime,
    params: dict[str, Any],
) -> str:
    agent_name = params.get("agent", "") or "build"
    system_content = await _system_prompt(runtime, params.get("system_prompt", ""), agent_name)
    system_message = SystemMessage(content=system_content)
    from laffyhand.core.db.models import Session as SessionModel

    session = SessionModel(
        title=params.get("title", ""),
        cwd=params.get("cwd", os.getcwd()),
        provider=params.get("provider", ""),
        model=params.get("model", ""),
        agent_name=agent_name,
    )
    runtime.session_manager.set_pending_meta(
        session.id,
        title=session.title,
        cwd=session.cwd,
        provider=str(session.provider) if session.provider else "",
        model=str(session.model) if session.model else "",
        agent_name=session.agent_name,
    )
    state = AgentState(
        messages=[system_message],
        session_id=SessionID(session.id),
        usage=SessionUsage(context_size=runtime.context_size),
    )
    runtime.session_store.set(session.id, state)
    runtime._schedule_title_generation(session.id, "on_create")
    return session.id


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
                "agent": s.agent_name,
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
    if not is_streaming:
        is_streaming = await runtime.session_event_bus.has_subscribers(session_id)
    return {
        "session_id": state.session_id,
        "title": session.title if session else None,
        "model": session.model if session else "",
        "agent": session.agent_name if session else "",
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
                "agent": s.agent_name,
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
    runtime.session_store.set(new_session_id, state)
    runtime.session_store.pop(session_id)
    return {"session_id": new_session_id}


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


async def handle_session_subscribe(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> None:
    session_id: str = params.get("session_id", "")
    if not session_id:
        raise ValueError("session_id is required")

    state = runtime.get_state(session_id)
    if state is None:
        state = runtime.load_session_state(session_id)
    if state is None:
        raise ValueError(f"Session not found: {session_id}")

    logger.debug(f"Session subscribe started for {session_id} (conn={conn_id})")

    try:
        async with runtime.session_event_bus.subscribe(session_id) as stream:
            async for event in stream:
                params = event.model_dump(exclude_none=True)
                notif = Notification(method="event", params=params)
                try:
                    await transport.send(notif.json())
                except Exception:
                    logger.debug(
                        f"Session subscribe transport closed for {session_id} (conn={conn_id})"
                    )
                    break
    except asyncio.CancelledError:
        logger.info(f"Session subscribe cancelled for {session_id} (conn={conn_id})")
        raise
    except Exception:
        logger.exception(
            f"Session subscribe error for {session_id} (conn={conn_id})"
        )
    finally:
        logger.debug(f"Session subscribe ended for {session_id} (conn={conn_id})")
