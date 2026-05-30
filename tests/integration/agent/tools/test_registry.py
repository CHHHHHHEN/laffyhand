import asyncio
import unittest

from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.registry import ToolRegistry
from laffyhand.agent.tools.permission import PermissionManager


class CountTool(BaseTool):
    name = "count"
    description = "Count characters"
    max_result_size = 50

    def _input_schema(self) -> dict:
        return {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

    async def run(self, params: dict) -> str:
        return params.get("text", "")


class FailingTool(BaseTool):
    name = "fail"
    description = "Always fails"

    async def run(self, params: dict) -> str:
        raise RuntimeError("intentional failure")


class TestRegistryIntegration(unittest.TestCase):
    """Test ToolRegistry with PermissionManager + truncation together."""

    def test_permission_deny_before_truncation(self):
        pm = PermissionManager()
        pm.deny("count")
        registry = ToolRegistry(permission=pm)
        registry.register_tool(CountTool())
        result = asyncio.run(registry.run_tool("count", {"text": "x" * 100}))
        self.assertIn("not permitted", result)

    def test_truncation_applied(self):
        registry = ToolRegistry()
        registry.register_tool(CountTool())
        result = asyncio.run(registry.run_tool("count", {"text": "x" * 100}))
        self.assertIn("[Tool output truncated:", result)

    def test_new_tool_available_immediately(self):
        registry = ToolRegistry()
        registry.register_tool(CountTool())
        self.assertEqual(len(asyncio.run(registry.build_tool_definitions())), 1)
        registry.register_tool(CountTool())
        self.assertEqual(len(asyncio.run(registry.build_tool_definitions())), 1)

    def test_error_propagation(self):
        registry = ToolRegistry()
        registry.register_tool(FailingTool())
        with self.assertRaises(RuntimeError):
            asyncio.run(registry.run_tool("fail", {}))
