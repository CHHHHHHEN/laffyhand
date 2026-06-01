from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any


_JSONRPC_VERSION = "2.0"
MAX_MESSAGE_SIZE = 16 * 1024 * 1024  # 16 MB


def _validate_id(raw_id: Any) -> None:
    if not isinstance(raw_id, (str, int, float)) or isinstance(raw_id, bool):
        raise ValueError("JSON-RPC id must be a string or number")


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
CHAT_STEER = "chat/steer"
TOOLS_LIST = "tools/list"
SESSION_SEARCH = "session/search"
SESSION_SET_TITLE = "session/set_title"
SESSION_GENERATE_TITLE = "session/generate_title"
SESSION_ARCHIVE = "session/archive"
SUBAGENT_LIST_ACTIVE = "subagent/list_active"
USAGE_GET = "usage/get"
CONFIG_PROVIDERS = "config/providers"
MCP_STATUS = "mcp/status"
SESSION_SET_CONFIG = "session/set_config"
PERMISSION_RESPOND = "permission/respond"
TODO_LIST = "todo/list"
TODO_UPDATE = "todo/update"


@dataclass
class Error:
    code: int
    message: str
    data: dict[str, Any] | None = None

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


def to_dict(msg: JSONRPCMessage | Error) -> dict[str, Any]:
    if isinstance(msg, Notification):
        d: dict[str, Any] = {"method": msg.method, "jsonrpc": msg.jsonrpc}
        if msg.params is not None:
            d["params"] = msg.params
        return d
    d = asdict(msg)
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
        raise ValueError("Invalid JSON-RPC message")
    jsonrpc = obj.get("jsonrpc", _JSONRPC_VERSION)
    if jsonrpc != _JSONRPC_VERSION:
        raise ValueError(f"Unsupported JSON-RPC version: {jsonrpc}")
    has_id = "id" in obj
    has_method = "method" in obj
    has_result = "result" in obj
    has_error = "error" in obj
    if has_method and has_id:
        _validate_id(obj["id"])
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
        _validate_id(obj["id"])
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
    raise ValueError("Cannot classify JSON-RPC message")


# Standard JSON-RPC error codes
PARSE_ERROR = -32700
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603


