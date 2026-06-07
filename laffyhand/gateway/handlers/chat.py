from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

from loguru import logger

from laffyhand.core.models import (
    Finish,
    PermissionRequest,
    StepFinish,
    TextDelta,
)
from laffyhand.core.llm.specs.models import SystemMessage, UserMessage
from laffyhand.core.tools.permission import request_callback as _pm_callback
from laffyhand.gateway.protocol import Notification

if TYPE_CHECKING:
    from laffyhand.core.runtime import AgentRuntime
    from laffyhand.gateway.transport import Transport


async def _prepare_chat(
    runtime: AgentRuntime,
    params: dict[str, Any],
) -> str:
    message: str = params.get("message", "")
    if not message:
        raise ValueError("message is required")

    session_id: str | None = params.get("session_id")
    if not session_id:
        from laffyhand.gateway.handlers.session import _ensure_session

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


class ChatStreamSession:
    """Encapsulates the lifecycle of a streaming chat session.

    Manages permission callback setup/teardown, event streaming,
    error handling, background subagent event draining, and
    finish notification.
    """

    def __init__(
        self,
        runtime: AgentRuntime,
        session_id: str,
        transport: Transport,
        conn_id: str,
    ) -> None:
        self._runtime = runtime
        self._session_id = session_id
        self._transport = transport
        self._conn_id = conn_id
        self._finish_reason: str = ""
        self._usage_info: Any = None
        self._cancelled = False
        self._token: Any = None

    async def __aenter__(self) -> ChatStreamSession:
        self._token = _pm_callback.set(self._permission_callback)
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: object,
    ) -> None:
        _pm_callback.reset(self._token)

    async def run(self) -> None:
        """Run the stream loop inside the session lock."""
        async with self._runtime.get_session_lock(self._session_id):
            await self._stream()

    async def finish(self) -> None:
        """Send finish notification outside the session lock."""
        state = self._runtime.get_state(self._session_id)
        actual_sid = state.session_id if (state and state.session_id) else self._session_id
        await self._runtime._generate_title(actual_sid, "auto")

        session_dispatcher = getattr(self._transport, "dispatcher", None)
        if session_dispatcher is not None:
            session_dispatcher.unregister_session_stream(self._session_id)

        leftover_steer: str | None = None
        state = self._runtime.get_state(self._session_id)
        if state is not None:
            async with self._runtime.get_session_lock(self._session_id):
                if state.pending_steer:
                    leftover_steer = state.pending_steer
                    state.pending_steer = None

        done_params = Finish(
            reason=self._finish_reason,
            usage=self._usage_info,
            session_id=self._session_id,
            session_usage=state.usage.model_dump() if state and state.usage else None,
            leftover_steer=leftover_steer,
        ).model_dump(exclude_none=True)
        done = Notification(method="event", params=done_params)
        try:
            await self._transport.send(done.json())
        except Exception:
            logger.warning(
                "Failed to send finish event to client (connection may be closed)"
            )

    async def _stream(self) -> None:
        """Inner stream iteration with error and cancellation handling."""
        try:
            async for event in self._runtime.run_agent_turn(
                session_id=self._session_id,
                event_sink=self._event_sink,
            ):
                if self._runtime.subagent_manager:
                    bg = await self._runtime.subagent_manager.drain_events(self._session_id)
                    for be in bg:
                        await self._event_sink(be)

                notif = Notification(
                    method="event",
                    params=event.model_dump(exclude_none=True),
                )
                await self._transport.send(notif.json())

                if isinstance(event, StepFinish):
                    self._finish_reason = event.reason
                    self._usage_info = event.usage
        except asyncio.CancelledError:
            self._cancelled = True
            self._finish_reason = "cancelled"
            logger.info(
                f"Chat stream cancelled for session {self._session_id} (conn={self._conn_id})"
            )
        except Exception:
            logger.exception(
                f"Chat stream error for session {self._session_id} (conn={self._conn_id})"
            )
            err = Notification(
                method="event",
                params={"type": "error", "data": "Internal error during streaming"},
            )
            try:
                await self._transport.send(err.json())
            except Exception:
                logger.warning(
                    "Failed to send error event to client in chat stream"
                )
        finally:
            if self._runtime.subagent_manager:
                bg = await self._runtime.subagent_manager.drain_events(self._session_id)
                for be in bg:
                    try:
                        await self._event_sink(be)
                    except Exception:
                        logger.warning("Failed to relay background event")

            if self._cancelled:
                cancel = Notification(
                    method="event",
                    params={"type": "cancelled", "data": "Stream cancelled"},
                )
                await self._transport.send(cancel.json())

    async def _permission_callback(
        self, permission: str, pattern: str
    ) -> tuple[bool, str | None]:
        request_id = str(uuid.uuid4())
        event = asyncio.Event()
        self._runtime.session_store.pending_permissions[request_id] = (
            event,
            permission,
            pattern,
            None,
            None,
        )
        try:
            pr = PermissionRequest(
                request_id=request_id,
                permission=permission,
                pattern=pattern,
            )
            notif = Notification(method="event", params=pr.model_dump())
            await self._transport.send(notif.json())
            try:
                await asyncio.wait_for(event.wait(), timeout=300.0)
            except asyncio.TimeoutError:
                logger.warning(f"Permission request {request_id} timed out")
                return (False, None)
            _, _, _, result, reason = self._runtime.session_store.pending_permissions.get(
                request_id, (None, None, None, False, None)
            )
            return (bool(result), reason)
        finally:
            self._runtime.session_store.pending_permissions.pop(request_id, None)

    async def _event_sink(self, event: Any) -> None:
        notif = Notification(
            method="event", params=event.model_dump(exclude_none=True)
        )
        await self._transport.send(notif.json())


async def handle_chat_stream(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> None:
    session_id = await _prepare_chat(runtime, params)
    session = ChatStreamSession(runtime, session_id, transport, conn_id)
    async with session:
        await session.run()
        await session.finish()


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

    from laffyhand.gateway.dispatcher import Dispatcher

    dispatcher: Dispatcher | None = getattr(transport, "dispatcher", None)

    if dispatcher is not None and session_id:
        if await dispatcher.cancel_session_stream(session_id):
            logger.info(f"Streaming task cancelled for session {session_id}")
            return {"status": "cancelled"}

    if dispatcher is not None:
        if dispatcher.cancel_connection(conn_id):
            logger.info(f"Streaming task cancelled for connection {conn_id}")
            return {"status": "cancelled"}
        logger.debug(f"No active streaming task for connection {conn_id}")

    sse_canceller = getattr(transport, "sse_canceller", None)
    if sse_canceller is not None:
        if sse_canceller(conn_id):
            logger.info(f"SSE stream cancelled for connection {conn_id}")
            return {"status": "cancelled"}
        logger.debug(f"No active SSE stream for connection {conn_id}")

    if dispatcher is None and sse_canceller is None:
        logger.warning(
            f"Cancellation not supported for transport {type(transport).__name__} (conn={conn_id})"
        )

    return {"status": "no_active_stream"}
