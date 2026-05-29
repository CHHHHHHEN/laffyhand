import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock

from laffyhand.agent.mcp.client import MCPClient, MCPToolDef
from laffyhand.agent.mcp.service import MCPService, MCPWrappedTool, _normalize_schema


class TestMCPWrappedTool(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock(spec=MCPClient)
        self.client.name = "test-server"
        self.client.call_tool = AsyncMock(return_value="result")
        self.service = MagicMock(spec=MCPService)
        self.service.get_client.return_value = self.client
        self.service.reconnect = AsyncMock(return_value=True)
        td = MCPToolDef(name="list-files", description="List files in a directory", input_schema={"type": "object", "properties": {"path": {"type": "string"}}})
        self.tool = MCPWrappedTool("test-server", td, self.service)

    def test_tool_name_mangled(self):
        self.assertEqual(self.tool.name, "mcp_test-server_list_files")

    def test_tool_description(self):
        self.assertEqual(self.tool.description, "List files in a directory")

    def test_input_schema_preserved(self):
        schema = self.tool._input_schema()
        self.assertIn("path", schema.get("properties", {}))
        self.assertEqual(schema.get("type"), "object")

    def test_run_delegates_to_client(self):
        result = asyncio.run(self.tool.run({"path": "/tmp"}))
        self.client.call_tool.assert_called_once_with("list-files", {"path": "/tmp"})
        self.assertEqual(result, "result")

    def test_additional_properties_false(self):
        schema = self.tool._input_schema()
        self.assertFalse(schema.get("additionalProperties", True))

    def test_missing_type_defaults_to_object(self):
        td = MCPToolDef(name="t", description="", input_schema={"properties": {}})
        tool = MCPWrappedTool("srv", td, self.service)
        schema = tool._input_schema()
        self.assertEqual(schema["type"], "object")


class TestNormalizeSchema(unittest.TestCase):
    def test_passthrough_simple(self):
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        result = _normalize_schema(schema)
        self.assertEqual(result["properties"]["x"]["type"], "string")

    def test_nullable_type_list(self):
        schema = {"type": "object", "properties": {"x": {"type": ["string", "null"]}}}
        result = _normalize_schema(schema)
        self.assertEqual(result["properties"]["x"]["type"], "string")
        self.assertTrue(result["properties"]["x"]["nullable"])

    def test_nullable_any_of(self):
        schema = {"type": "object", "properties": {"x": {"anyOf": [{"type": "string"}, {"type": "null"}]}}}
        result = _normalize_schema(schema)
        self.assertEqual(result["properties"]["x"]["type"], "string")
        self.assertTrue(result["properties"]["x"]["nullable"])
        self.assertNotIn("anyOf", result["properties"]["x"])

    def test_nullable_one_of(self):
        schema = {"type": "object", "properties": {"x": {"oneOf": [{"type": "number"}, {"type": "null"}]}}}
        result = _normalize_schema(schema)
        self.assertEqual(result["properties"]["x"]["type"], "number")
        self.assertTrue(result["properties"]["x"]["nullable"])
        self.assertNotIn("oneOf", result["properties"]["x"])

    def test_preserves_non_nullable_any_of(self):
        schema = {"type": "object", "properties": {"x": {"anyOf": [{"type": "string"}, {"type": "number"}]}}}
        result = _normalize_schema(schema)
        self.assertIn("anyOf", result["properties"]["x"])
        self.assertNotIn("nullable", result["properties"]["x"])

    def test_recursive_nested_properties(self):
        schema = {
            "type": "object",
            "properties": {
                "outer": {
                    "type": "object",
                    "properties": {
                        "inner": {"type": ["string", "null"]},
                    },
                },
            },
        }
        result = _normalize_schema(schema)
        inner = result["properties"]["outer"]["properties"]["inner"]
        self.assertEqual(inner["type"], "string")
        self.assertTrue(inner["nullable"])

    def test_recursive_items(self):
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": ["string", "null"]},
                },
            },
        }
        result = _normalize_schema(schema)
        self.assertEqual(result["properties"]["items"]["items"]["type"], "string")
        self.assertTrue(result["properties"]["items"]["items"]["nullable"])

    def test_recursive_additional_properties(self):
        schema = {
            "type": "object",
            "properties": {
                "dict": {
                    "type": "object",
                    "additionalProperties": {"type": ["integer", "null"]},
                },
            },
        }
        result = _normalize_schema(schema)
        ap = result["properties"]["dict"]["additionalProperties"]
        self.assertEqual(ap["type"], "integer")
        self.assertTrue(ap["nullable"])

    def test_recursive_all_of(self):
        schema = {
            "type": "object",
            "properties": {
                "x": {
                    "allOf": [
                        {"type": "object", "properties": {"y": {"type": ["string", "null"]}}},
                    ],
                },
            },
        }
        result = _normalize_schema(schema)
        y = result["properties"]["x"]["allOf"][0]["properties"]["y"]
        self.assertEqual(y["type"], "string")
        self.assertTrue(y["nullable"])

    def test_recursive_defs(self):
        schema = {
            "type": "object",
            "properties": {
                "ref": {"$ref": "#/$defs/MyType"},
            },
            "$defs": {
                "MyType": {
                    "type": "object",
                    "properties": {
                        "field": {"type": ["number", "null"]},
                    },
                },
            },
        }
        result = _normalize_schema(schema)
        field = result["$defs"]["MyType"]["properties"]["field"]
        self.assertEqual(field["type"], "number")
        self.assertTrue(field["nullable"])
