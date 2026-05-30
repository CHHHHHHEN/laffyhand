from __future__ import annotations

import json

import pytest

from laffyhand.gateway.protocol import (
    Request, Response, Notification, ErrorResponse, Error,
    from_json,
    PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS,
    INTERNAL_ERROR, OVERLOADED, STREAM_CANCELLED, MAX_MESSAGE_SIZE,
    GatewayConfig,
    INITIALIZE, SHUTDOWN, SESSION_CREATE, SESSION_LIST, SESSION_LOAD,
    SESSION_DELETE, SESSION_FORK, CHAT, CHAT_STREAM, CHAT_CANCEL, TOOLS_LIST,
)

_REQUEST_JSON = '{"jsonrpc":"2.0","id":1,"method":"test","params":{"key":"val"}}'
_NOTIFICATION_JSON = '{"jsonrpc":"2.0","method":"notify"}'
_RESPONSE_JSON = '{"jsonrpc":"2.0","id":1,"result":"ok"}'
_ERROR_JSON = '{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"not found","data":null}}'


class TestRequest:
    def test_create(self):
        r = Request(id=1, method="test", params={"a": 1})
        assert r.id == 1
        assert r.method == "test"
        assert r.params == {"a": 1}
        assert r.jsonrpc == "2.0"

    def test_create_minimal(self):
        r = Request(id="abc", method="ping")
        assert r.params is None

    def test_to_json(self):
        r = Request(id=1, method="test", params={"key": "val"})
        data = json.loads(r.json())
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["method"] == "test"
        assert data["params"] == {"key": "val"}


class TestResponse:
    def test_create(self):
        r = Response(id=1, result="hello")
        assert r.id == 1
        assert r.result == "hello"

    def test_create_none_result(self):
        r = Response(id=1, result=None)
        assert r.result is None

    def test_to_json(self):
        r = Response(id=1, result={"answer": 42})
        data = json.loads(r.json())
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["result"] == {"answer": 42}


class TestNotification:
    def test_create(self):
        n = Notification(method="event", params={"type": "update"})
        assert n.method == "event"
        assert n.params == {"type": "update"}

    def test_to_json(self):
        n = Notification(method="event")
        data = json.loads(n.json())
        assert data["method"] == "event"


class TestErrorResponse:
    def test_create(self):
        err = ErrorResponse(id=1, error=Error(code=-32601, message="not found"))
        assert err.id == 1
        assert err.error.code == -32601
        assert err.error.message == "not found"

    def test_with_data(self):
        err = ErrorResponse(id=None, error=Error(code=-32700, message="parse error", data={"detail": "bad json"}))
        assert err.error.data == {"detail": "bad json"}

    def test_to_json(self):
        err = ErrorResponse(id=1, error=Error(code=-32601, message="not found"))
        data = json.loads(err.json())
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["error"]["code"] == -32601


class TestFromJson:
    def test_request(self):
        msg = from_json(_REQUEST_JSON)
        assert isinstance(msg, Request)
        assert msg.id == 1
        assert msg.method == "test"
        assert msg.params == {"key": "val"}

    def test_response(self):
        msg = from_json(_RESPONSE_JSON)
        assert isinstance(msg, Response)
        assert msg.id == 1
        assert msg.result == "ok"

    def test_notification(self):
        msg = from_json(_NOTIFICATION_JSON)
        assert isinstance(msg, Notification)
        assert msg.method == "notify"

    def test_error_response(self):
        msg = from_json(_ERROR_JSON)
        assert isinstance(msg, ErrorResponse)
        assert msg.id == 1
        assert msg.error.code == -32601
        assert msg.error.message == "not found"
        assert msg.error.data is None

    def test_string_id(self):
        msg = from_json('{"jsonrpc":"2.0","id":"req-1","method":"do"}')
        assert isinstance(msg, Request)
        assert msg.id == "req-1"

    def test_null_params(self):
        msg = from_json('{"jsonrpc":"2.0","id":1,"method":"test","params":null}')
        assert isinstance(msg, Request)
        assert msg.params is None

    def test_no_params(self):
        msg = from_json('{"jsonrpc":"2.0","id":1,"method":"test"}')
        assert isinstance(msg, Request)
        assert msg.params is None

    def test_invalid_json(self):
        with pytest.raises(ValueError):
            from_json("not json")

    def test_not_dict(self):
        with pytest.raises(ValueError):
            from_json("[1,2,3]")

    def test_wrong_version(self):
        with pytest.raises(ValueError, match="1.0"):
            from_json('{"jsonrpc":"1.0","id":1,"method":"test"}')

    def test_empty_json(self):
        with pytest.raises(ValueError):
            from_json("null")

    def test_unclassifiable(self):
        with pytest.raises(ValueError):
            from_json('{"jsonrpc":"2.0"}')

    def test_result_without_id(self):
        with pytest.raises(ValueError):
            from_json('{"jsonrpc":"2.0","result":"ok"}')

    def test_request_with_explicit_jsonrpc(self):
        msg = from_json('{"jsonrpc":"2.0","id":1,"method":"hello"}')
        assert msg.jsonrpc == "2.0"


class TestMaxMessageSize:
    def test_exceeds_limit(self):
        data = "x" * (MAX_MESSAGE_SIZE + 1)
        with pytest.raises(ValueError, match="too large"):
            from_json(data)

    def test_at_limit(self):
        data = "x" * MAX_MESSAGE_SIZE
        with pytest.raises(json.JSONDecodeError):
            from_json(data)

    def test_under_limit(self):
        data = '{"jsonrpc":"2.0","id":1,"method":"ok"}'
        msg = from_json(data)
        assert isinstance(msg, Request)


class TestErrorCodes:
    def test_standard_codes(self):
        assert PARSE_ERROR == -32700
        assert INVALID_REQUEST == -32600
        assert METHOD_NOT_FOUND == -32601
        assert INVALID_PARAMS == -32602
        assert INTERNAL_ERROR == -32603

    def test_custom_codes(self):
        assert OVERLOADED == -32001
        assert STREAM_CANCELLED == -32002


class TestErrorJson:
    def test_error_json(self):
        e = Error(code=-32601, message="not found", data={"detail": "x"})
        data = json.loads(e.json())
        assert data["code"] == -32601
        assert data["message"] == "not found"
        assert data["data"] == {"detail": "x"}

    def test_error_json_no_data(self):
        e = Error(code=-32601, message="not found")
        data = json.loads(e.json())
        assert data["code"] == -32601
        assert data["message"] == "not found"
        assert data["data"] is None


class TestGatewayConfig:
    def test_defaults(self):
        cfg = GatewayConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 9090
        assert cfg.max_message_size == MAX_MESSAGE_SIZE

    def test_custom(self):
        cfg = GatewayConfig(host="0.0.0.0", port=8080, max_message_size=4096)
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8080
        assert cfg.max_message_size == 4096


class TestMethodConstants:
    def test_values(self):
        assert INITIALIZE == "initialize"
        assert SHUTDOWN == "shutdown"
        assert SESSION_CREATE == "session/create"
        assert SESSION_LIST == "session/list"
        assert SESSION_LOAD == "session/load"
        assert SESSION_DELETE == "session/delete"
        assert SESSION_FORK == "session/fork"
        assert CHAT == "chat"
        assert CHAT_STREAM == "chat_stream"
        assert CHAT_CANCEL == "chat/cancel"
        assert TOOLS_LIST == "tools/list"
