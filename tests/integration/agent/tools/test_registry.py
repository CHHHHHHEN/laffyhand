import unittest

from laffyhand.agent.schemas import ToolResultContent
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.registry import ToolRegistry
from laffyhand.agent.tools.permission import PermissionManager


class CountTool(BaseTool):
    name = "count"
    description = "Count characters"
    max_result_size = 50

    def _input_schema(self) -> dict:
        return {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

    def run(self, params: dict) -> ToolResultContent:
        return ToolResultContent(tool_call_id="", tool_name=self.name, result=params.get("text", ""))


class FailingTool(BaseTool):
    name = "fail"
    description = "Always fails"

    def run(self, params: dict) -> ToolResultContent:
        raise RuntimeError("intentional failure")


class TestRegistryIntegration(unittest.TestCase):
    """Test ToolRegistry with PermissionManager + truncation together."""

    def test_permission_deny_before_truncation(self):
        pm = PermissionManager()
        pm.deny("count")
        registry = ToolRegistry(permission=pm)
        registry.register_tool(CountTool())
        result = registry.run_tool("count", {"text": "x" * 100})
        self.assertIn("not permitted", result.result)
        # Even though text > max_result_size, permission check comes first

    def test_truncation_applied(self):
        registry = ToolRegistry()
        registry.register_tool(CountTool())
        result = registry.run_tool("count", {"text": "x" * 100})
        self.assertIn("[Tool output truncated:", result.result)

    def test_tool_call_id_preserved_through_registry(self):
        registry = ToolRegistry()
        registry.register_tool(CountTool())
        result = registry.run_tool("count", {"text": "hello"}, tool_call_id="call_abc")
        self.assertEqual(result.tool_call_id, "call_abc")
        self.assertEqual(result.tool_name, "count")

    def test_new_tool_available_immediately(self):
        registry = ToolRegistry()
        registry.register_tool(CountTool())
        self.assertEqual(len(registry.build_tool_definitions()), 1)
        registry.register_tool(CountTool())
        self.assertEqual(len(registry.build_tool_definitions()), 1)  # overwrite

    def test_error_propagation(self):
        registry = ToolRegistry()
        registry.register_tool(FailingTool())
        with self.assertRaises(RuntimeError):
            registry.run_tool("fail", {})
