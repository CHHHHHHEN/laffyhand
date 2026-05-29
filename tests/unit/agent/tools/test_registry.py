import unittest

from laffyhand.agent.schemas import ToolResultContent
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.registry import ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo back input"
    max_result_size = 100

    def _input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    def run(self, params: dict) -> ToolResultContent:
        return ToolResultContent(tool_call_id="", tool_name=self.name, result=params.get("text", ""))


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register_tool(EchoTool())

    def test_register_and_definitions(self):
        defs = self.registry.build_tool_definitions()
        self.assertEqual(len(defs), 1)
        self.assertEqual(defs[0].name, "echo")
        self.assertEqual(defs[0].description, "Echo back input")
        self.assertIn("text", str(defs[0].input_schema))

    def test_run_tool(self):
        result = self.registry.run_tool("echo", {"text": "hello"})
        self.assertEqual(result.result, "hello")
        self.assertEqual(result.tool_name, "echo")

    def test_run_tool_sets_call_id(self):
        result = self.registry.run_tool("echo", {"text": "hi"}, tool_call_id="call_123")
        self.assertEqual(result.tool_call_id, "call_123")

    def test_build_tool_prompt(self):
        prompt = self.registry.build_tool_prompt()
        self.assertIn("echo", prompt)
        self.assertIn("Echo back input", prompt)

    def test_unregister(self):
        self.registry.unregister_tool("echo")
        self.assertEqual(len(self.registry.build_tool_definitions()), 0)

    def test_cache_invalidated_on_register(self):
        defs1 = self.registry.build_tool_definitions()
        self.registry.register_tool(EchoTool())
        defs2 = self.registry.build_tool_definitions()
        self.assertIsNot(defs1, defs2)

    def test_run_unknown_tool_returns_error_message(self):
        result = self.registry.run_tool("nonexistent", {})
        self.assertIn("not registered", result.result)

    def test_run_unregistered_tool_after_unregister(self):
        self.registry.unregister_tool("echo")
        result = self.registry.run_tool("echo", {})
        self.assertIn("not registered", result.result)
