import unittest

from laffyhand.agent.mcp.client import MCPToolDef


class TestMCPToolDef(unittest.TestCase):
    def test_basic_fields(self):
        td = MCPToolDef(
            name="read_file", description="Read a file", input_schema={"type": "object"}
        )
        self.assertEqual(td.name, "read_file")
        self.assertEqual(td.description, "Read a file")
        self.assertEqual(td.input_schema, {"type": "object"})

    def test_empty_description(self):
        td = MCPToolDef(name="tool", description="", input_schema={})
        self.assertEqual(td.description, "")
