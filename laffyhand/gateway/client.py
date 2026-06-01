from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, cast

from loguru import logger

from laffyhand.agent.loop import (
    StepStart,
    TextStart,
    TextDelta,
    TextEnd,
    ReasoningStart,
    ReasoningDelta,
    ReasoningEnd,
    ToolCall,
    ToolResult,
    ToolError,
    StepFinish,
    Finish,
    ProviderError,
    Compacting,
    StreamEvent,
)
from laffyhand.gateway.protocol import (
    Request,
    Response,
    ErrorResponse,
    Notification,
    from_json,
)
from laffyhand.gateway.transport import Transport

_RPC_TIMEOUT = 120.0


class RPCError(Exception):
    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"RPC error ({code}): {message}")


# ── Event reconstruction ───────────────────────────────────────
# Map type strings to the corresponding Pydantic model.

_EVENT_TYPE_MAP: dict[str, type[StreamEvent]] = {
    "step-start": StepStart,
    "text-start": TextStart,
    "text-delta": TextDelta,
    "text-end": TextEnd,
    "reasoning-start": ReasoningStart,
    "reasoning-delta": ReasoningDelta,
    "reasoning-end": ReasoningEnd,
    "tool-call": ToolCall,
    "tool-result": ToolResult,
    "tool-error": ToolError,
    "step-finish": StepFinish,
    "finish": Finish,
    "provider-error": ProviderError,
    "compacting": Compacting,
}


def event_from_params(params: dict[str, Any]) -> StreamEvent:
    type_ = params.get("type", "")
    cls = _EVENT_TYPE_MAP.get(type_)
    if cls is None:
        raise ValueError(f"Unknown event type: {type_}")
    # Pass all keys; pydantic ignores extras via model_config (extra="forbid" is default,
    # but we allow extra keys by constructing with only the known fields).
    # Use model_validate to handle aliases/strictness gracefully.
    return cls.model_validate(params)


# ── Client ─────────────────────────────────────────────────────


class GatewayClient:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _recv_with_timeout(self) -> str:
        raw = await asyncio.wait_for(self._transport.recv(), timeout=_RPC_TIMEOUT)
        if not raw:
            raise ConnectionError("Transport closed")
        return raw

    async def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        req_id = self._next_id()
        await self._transport.send(
            Request(id=req_id, method=method, params=params).json()
        )
        while True:
            raw = await self._recv_with_timeout()
            msg = from_json(raw)
            if isinstance(msg, Response) and msg.id == req_id:
                return msg.result
            if isinstance(msg, ErrorResponse) and msg.id == req_id:
                raise RPCError(msg.error.code, msg.error.message)
            logger.warning(
                f"Ignoring unexpected message (id={msg.id if hasattr(msg, 'id') else 'N/A'}) "
                f"while waiting for response to id={req_id}"
            )

    async def _request_stream(
        self, method: str, params: dict[str, Any] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        req_id = self._next_id()
        await self._transport.send(
            Request(id=req_id, method=method, params=params).json()
        )
        while True:
            raw = await self._recv_with_timeout()
            msg = from_json(raw)
            if isinstance(msg, ErrorResponse) and msg.id == req_id:
                raise RPCError(msg.error.code, msg.error.message)
            if isinstance(msg, Response) and msg.id == req_id:
                logger.warning(
                    f"Received unexpected Response (id={req_id}) in stream, ignoring"
                )
                continue
            if isinstance(msg, Notification) and msg.method == "event":
                if msg.params is None:
                    logger.warning("Received event notification with null params")
                    continue
                yield msg.params
                if msg.params.get("type") == "finish":
                    return

    async def initialize(self) -> dict[str, Any]:
        result = await self._request("initialize")
        return cast(dict[str, Any], result)

    async def shutdown(self) -> None:
        await self._request("shutdown")

    async def create_session(
        self,
        system_prompt: str = "",
        title: str = "",
        cwd: str = "",
        provider: str = "",
        model: str = "",
    ) -> str:
        result = await self._request(
            "session/create",
            {
                "system_prompt": system_prompt,
                "title": title,
                "cwd": cwd,
                "provider": provider,
                "model": model,
            },
        )
        return cast(str, result["session_id"])

    async def list_sessions(
        self,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        result = await self._request(
            "session/list",
            {
                "status": status,
                "limit": limit,
                "offset": offset,
            },
        )
        return cast(list[dict[str, Any]], result["sessions"])

    async def load_session(self, session_id: str) -> dict[str, Any]:
        result = await self._request("session/load", {"session_id": session_id})
        return cast(dict[str, Any], result)

    async def delete_session(self, session_id: str) -> None:
        await self._request("session/delete", {"session_id": session_id})

    async def fork_session(self) -> str:
        result = await self._request("session/fork")
        return cast(str, result["session_id"])

    async def search_sessions(
        self, query: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        result = await self._request("session/search", {"query": query, "limit": limit})
        return cast(list[dict[str, Any]], result["sessions"])

    async def set_session_title(
        self, title: str, session_id: str | None = None
    ) -> None:
        params: dict[str, Any] = {"title": title}
        if session_id is not None:
            params["session_id"] = session_id
        await self._request("session/set_title", params)

    async def generate_session_title(self) -> str | None:
        result = await self._request("session/generate_title")
        return cast(str | None, result.get("title"))

    async def archive_session(self, session_id: str = "") -> None:
        params: dict[str, Any] = {}
        if session_id:
            params["session_id"] = session_id
        await self._request("session/archive", params)

    async def chat_stream(self, message: str) -> AsyncIterator[StreamEvent]:
        async for params in self._request_stream("chat/stream", {"message": message}):
            if params.get("type") == "finish":
                yield event_from_params(params)
                return
            yield event_from_params(params)

    async def cancel_chat(self, session_id: str | None = None) -> None:
        params: dict[str, Any] = {}
        if session_id:
            params["session_id"] = session_id
        await self._request("chat/cancel", params)

    async def steer_chat(self, message: str, session_id: str | None = None) -> None:
        params: dict[str, Any] = {"message": message}
        if session_id:
            params["session_id"] = session_id
        await self._request("chat/steer", params)

    async def list_active_subagents(self) -> list[dict[str, Any]]:
        result = await self._request("subagent/list_active")
        return cast(list[dict[str, Any]], result["subagents"])

    async def get_usage(self) -> dict[str, Any]:
        result = await self._request("usage/get")
        return cast(dict[str, Any], result)
