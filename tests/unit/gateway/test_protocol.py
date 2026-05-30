from __future__ import annotations

import json
import unittest

from laffyhand.gateway.protocol import (
    Request, Response, Notification, ErrorResponse, Error,
    from_json, to_json, to_dict,
    PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS,
    INTERNAL_ERROR, OVERLOADED, STREAM_CANCELLED, MAX_MESSAGE_SIZE,
)

_REQUEST_JSON = '{"jsonrpc":"2.0","id":1,"method":"test","params":{"key":"val"}}'
_NOTIFICATION_JSON = '{"jsonrpc":"2.0","method":"notify"}'
_RESPONSE_JSON = '{"jsonrpc":"2.0","id":1,"result":"ok"}'
_ERROR_JSON = '{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"not found","data":null}}'


class TestRequest(unittest.TestCase):
    def test_create(self):
        r = Request(id=1, method="test", params={"a": 1})
        self.assertEqual(r.id, 1)
        self.assertEqual(r.method, "test")
        self.assertEqual(r.params, {"a": 1})
        self.assertEqual(r.jsonrpc, "2.0")

    def test_create_minimal(self):
        r = Request(id="abc", method="ping")
        self.assertIsNone(r.params)

    def test_to_json(self):
        r = Request(id=1, method="test", params={"key": "val"})
        data = json.loads(r.json())
        self.assertEqual(data["jsonrpc"], "2.0")
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["method"], "test")
        self.assertEqual(data["params"], {"key": "val"})


class TestResponse(unittest.TestCase):
    def test_create(self):
        r = Response(id=1, result="hello")
        self.assertEqual(r.id, 1)
        self.assertEqual(r.result, "hello")

    def test_create_none_result(self):
        r = Response(id=1, result=None)
        self.assertIsNone(r.result)

    def test_to_json(self):
        r = Response(id=1, result={"answer": 42})
        data = json.loads(r.json())
        self.assertEqual(data["jsonrpc"], "2.0")
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["result"], {"answer": 42})


class TestNotification(unittest.TestCase):
    def test_create(self):
        n = Notification(method="event", params={"type": "update"})
        self.assertEqual(n.method, "event")
        self.assertEqual(n.params, {"type": "update"})

    def test_to_json(self):
        n = Notification(method="event")
        data = json.loads(n.json())
        self.assertEqual(data["method"], "event")


class TestErrorResponse(unittest.TestCase):
    def test_create(self):
        err = ErrorResponse(id=1, error=Error(code=-32601, message="not found"))
        self.assertEqual(err.id, 1)
        self.assertEqual(err.error.code, -32601)
        self.assertEqual(err.error.message, "not found")

    def test_with_data(self):
        err = ErrorResponse(id=None, error=Error(code=-32700, message="parse error", data={"detail": "bad json"}))
        self.assertEqual(err.error.data, {"detail": "bad json"})

    def test_to_json(self):
        err = ErrorResponse(id=1, error=Error(code=-32601, message="not found"))
        data = json.loads(err.json())
        self.assertEqual(data["jsonrpc"], "2.0")
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["error"]["code"], -32601)


class TestFromJson(unittest.TestCase):
    def test_request(self):
        msg = from_json(_REQUEST_JSON)
        self.assertIsInstance(msg, Request)
        self.assertEqual(msg.id, 1)
        self.assertEqual(msg.method, "test")
        self.assertEqual(msg.params, {"key": "val"})

    def test_response(self):
        msg = from_json(_RESPONSE_JSON)
        self.assertIsInstance(msg, Response)
        self.assertEqual(msg.id, 1)
        self.assertEqual(msg.result, "ok")

    def test_notification(self):
        msg = from_json(_NOTIFICATION_JSON)
        self.assertIsInstance(msg, Notification)
        self.assertEqual(msg.method, "notify")

    def test_error_response(self):
        msg = from_json(_ERROR_JSON)
        self.assertIsInstance(msg, ErrorResponse)
        self.assertEqual(msg.id, 1)
        self.assertEqual(msg.error.code, -32601)
        self.assertEqual(msg.error.message, "not found")
        self.assertIsNone(msg.error.data)

    def test_string_id(self):
        msg = from_json('{"jsonrpc":"2.0","id":"req-1","method":"do"}')
        self.assertIsInstance(msg, Request)
        self.assertEqual(msg.id, "req-1")

    def test_null_params(self):
        msg = from_json('{"jsonrpc":"2.0","id":1,"method":"test","params":null}')
        self.assertIsInstance(msg, Request)
        self.assertIsNone(msg.params)

    def test_no_params(self):
        msg = from_json('{"jsonrpc":"2.0","id":1,"method":"test"}')
        self.assertIsInstance(msg, Request)
        self.assertIsNone(msg.params)

    def test_invalid_json(self):
        with self.assertRaises(ValueError):
            from_json("not json")

    def test_not_dict(self):
        with self.assertRaises(ValueError):
            from_json("[1,2,3]")

    def test_wrong_version(self):
        with self.assertRaises(ValueError) as ctx:
            from_json('{"jsonrpc":"1.0","id":1,"method":"test"}')
        self.assertIn("1.0", str(ctx.exception))

    def test_empty_json(self):
        with self.assertRaises(ValueError):
            from_json("null")

    def test_unclassifiable(self):
        with self.assertRaises(ValueError):
            from_json('{"jsonrpc":"2.0"}')

    def test_result_without_id(self):
        with self.assertRaises(ValueError):
            from_json('{"jsonrpc":"2.0","result":"ok"}')

    def test_request_with_explicit_jsonrpc(self):
        msg = from_json('{"jsonrpc":"2.0","id":1,"method":"hello"}')
        self.assertEqual(msg.jsonrpc, "2.0")


class TestMaxMessageSize(unittest.TestCase):
    def test_exceeds_limit(self):
        data = "x" * (MAX_MESSAGE_SIZE + 1)
        with self.assertRaises(ValueError) as ctx:
            from_json(data)
        self.assertIn("too large", str(ctx.exception).lower())

    def test_at_limit(self):
        data = "x" * MAX_MESSAGE_SIZE
        with self.assertRaises(json.JSONDecodeError):
            from_json(data)

    def test_under_limit(self):
        data = '{"jsonrpc":"2.0","id":1,"method":"ok"}'
        msg = from_json(data)
        self.assertIsInstance(msg, Request)


class TestErrorCodes(unittest.TestCase):
    def test_standard_codes(self):
        self.assertEqual(PARSE_ERROR, -32700)
        self.assertEqual(INVALID_REQUEST, -32600)
        self.assertEqual(METHOD_NOT_FOUND, -32601)
        self.assertEqual(INVALID_PARAMS, -32602)
        self.assertEqual(INTERNAL_ERROR, -32603)

    def test_custom_codes(self):
        self.assertEqual(OVERLOADED, -32001)
        self.assertEqual(STREAM_CANCELLED, -32002)


class TestErrorJson(unittest.TestCase):
    def test_error_json(self):
        e = Error(code=-32601, message="not found", data={"detail": "x"})
        data = json.loads(e.json())
        self.assertEqual(data["code"], -32601)
        self.assertEqual(data["message"], "not found")
        self.assertEqual(data["data"], {"detail": "x"})

    def test_error_json_no_data(self):
        e = Error(code=-32601, message="not found")
        data = json.loads(e.json())
        self.assertEqual(data["code"], -32601)
        self.assertIsNone(data["data"])
