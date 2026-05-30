from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any


_JSONRPC_VERSION = "2.0"
MAX_MESSAGE_SIZE = 16 * 1024 * 1024  # 16 MB

# RPC method names
INITIALIZE = "initialize"
SHUTDOWN = "shutdown"
SESSION_CREATE = "session/create"
SESSION_LIST = "session/list"
SESSION_LOAD = "session/load"
SESSION_DELETE = "session/delete"
SESSION_FORK = "session/fork"
CHAT = "chat"
CHAT_STREAM = "chat/stream"
CHAT_CANCEL = "chat/cancel"
TOOLS_LIST = "tools/list"


@dataclass
class Error:
    code: int
    message: str
    data: Any = None

    def json(self) -> str:
        return to_json(self)


@dataclass
class Request:
    id: str | int
    method: str
    params: dict[str, Any] | None = None
    jsonrpc: str = _JSONRPC_VERSION

    def json(self) -> str:
        return to_json(self)


@dataclass
class Response:
    id: str | int
    result: Any = None
    jsonrpc: str = _JSONRPC_VERSION

    def json(self) -> str:
        return to_json(self)


@dataclass
class ErrorResponse:
    id: str | int | None
    error: Error
    jsonrpc: str = _JSONRPC_VERSION

    def json(self) -> str:
        return to_json(self)


@dataclass
class Notification:
    method: str
    params: dict[str, Any] | None = None
    jsonrpc: str = _JSONRPC_VERSION

    def json(self) -> str:
        return to_json(self)


JSONRPCMessage = Request | Response | ErrorResponse | Notification


def _omit(d: dict, keys: set[str]) -> dict:
    return {k: v for k, v in d.items() if k not in keys}


def to_dict(msg: JSONRPCMessage | Error) -> dict[str, Any]:
    d = asdict(msg)
    if isinstance(msg, Notification):
        return _omit(d, {"jsonrpc"})
    return d


def to_json(msg: JSONRPCMessage | Error) -> str:
    return json.dumps(to_dict(msg), default=str, ensure_ascii=False)


def from_json(data: str) -> JSONRPCMessage:
    if len(data) > MAX_MESSAGE_SIZE:
        raise ValueError(
            f"Message too large: {len(data)} bytes (max {MAX_MESSAGE_SIZE})"
        )
    obj = json.loads(data)
    if not isinstance(obj, dict):
        raise ValueError(f"Invalid JSON-RPC message: {data!r}")
    jsonrpc = obj.get("jsonrpc", _JSONRPC_VERSION)
    if jsonrpc != _JSONRPC_VERSION:
        raise ValueError(f"Unsupported JSON-RPC version: {jsonrpc}")
    has_id = "id" in obj
    has_method = "method" in obj
    has_result = "result" in obj
    has_error = "error" in obj
    if has_method and has_id:
        return Request(
            id=obj["id"],
            method=obj["method"],
            params=obj.get("params"),
        )
    if has_method and not has_id:
        return Notification(
            method=obj["method"],
            params=obj.get("params"),
        )
    if has_result and has_id:
        return Response(
            id=obj["id"],
            result=obj["result"],
        )
    if has_error and has_id:
        err = obj["error"]
        return ErrorResponse(
            id=obj["id"],
            error=Error(
                code=err["code"],
                message=err["message"],
                data=err.get("data"),
            ),
        )
    raise ValueError(f"Cannot classify JSON-RPC message: {data!r}")


@dataclass
class GatewayConfig:
    host: str = "127.0.0.1"
    port: int = 9090
    max_message_size: int = MAX_MESSAGE_SIZE


# Standard JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Custom error codes
OVERLOADED = -32001
STREAM_CANCELLED = -32002
