from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from laffyhand.agent.loop import AgentEvent
from laffyhand.agent.schemas import Usage
from laffyhand.gateway.protocol import (
    Request, Response, ErrorResponse, Notification, from_json,
)
from laffyhand.gateway.transport import Transport

_RPC_TIMEOUT = 120.0


class RPCError(Exception):
    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"RPC error ({code}): {message}")


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
            if isinstance(msg, Notification) and msg.method == "event":
                if msg.params is None:
                    logger.warning("Received event notification with null params")
                    continue
                yield msg.params
                if msg.params.get("type") == "finish":
                    return

    async def initialize(self) -> dict[str, Any]:
        result = await self._request("initialize")
        return result  # type: ignore[return-value]

    async def shutdown(self) -> None:
        await self._request("shutdown")

    async def create_session(
        self,
        system_prompt: str = "",
        title: str = "",
        cwd: str = "",
        model: str = "",
    ) -> str:
        result = await self._request("session/create", {
            "system_prompt": system_prompt,
            "title": title,
            "cwd": cwd,
            "model": model,
        })
        return result["session_id"]  # type: ignore[return-value]

    async def list_sessions(
        self,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        result = await self._request("session/list", {
            "status": status,
            "limit": limit,
            "offset": offset,
        })
        return result["sessions"]  # type: ignore[return-value]

    async def load_session(self, session_id: str) -> dict[str, Any]:
        result = await self._request("session/load", {"session_id": session_id})
        return result  # type: ignore[return-value]

    async def delete_session(self, session_id: str) -> None:
        await self._request("session/delete", {"session_id": session_id})

    async def fork_session(self) -> str:
        result = await self._request("session/fork")
        return result["session_id"]  # type: ignore[return-value]

    async def search_sessions(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        result = await self._request("session/search", {"query": query, "limit": limit})
        return result["sessions"]  # type: ignore[return-value]

    async def set_session_title(self, title: str, session_id: str | None = None) -> None:
        params: dict[str, Any] = {"title": title}
        if session_id is not None:
            params["session_id"] = session_id
        await self._request("session/set_title", params)

    async def generate_session_title(self) -> str | None:
        result = await self._request("session/generate_title")
        return result.get("title")  # type: ignore[return-value]

    async def archive_session(self, session_id: str = "") -> None:
        params: dict[str, Any] = {}
        if session_id:
            params["session_id"] = session_id
        await self._request("session/archive", params)

    async def chat_stream(self, message: str) -> AsyncIterator[AgentEvent]:
        async for params in self._request_stream("chat_stream", {"message": message}):
            if params.get("type") == "finish":
                yield AgentEvent(
                    type="content",
                    data="",
                    finish_reason=params.get("finish_reason"),
                    usage=Usage(**params["usage"]) if params.get("usage") else None,
                    session_usage=params.get("session_usage"),
                )
                return
            usage = None
            raw_usage = params.get("usage")
            if raw_usage:
                usage = Usage(**raw_usage)
            yield AgentEvent(
                type=params.get("type", "content"),  # type: ignore[arg-type]
                data=params.get("data", ""),
                finish_reason=params.get("finish_reason"),
                usage=usage,
                session_usage=params.get("session_usage"),
            )

    async def cancel_chat(self) -> None:
        await self._request("chat/cancel")

    async def list_active_subagents(self) -> list[dict[str, Any]]:
        result = await self._request("subagent/list_active")
        return result["subagents"]  # type: ignore[return-value]

    async def get_usage(self) -> dict[str, Any]:
        result = await self._request("usage/get")
        return result  # type: ignore[return-value]
