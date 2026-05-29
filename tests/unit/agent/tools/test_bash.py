import unittest
from laffyhand.agent.tools.bash import BashTool


class TestBashTool(unittest.TestCase):
    def setUp(self):
        self.tool = BashTool()

    def test_echo(self):
        result = self.tool.run({"command": "echo hello"})
        self.assertEqual(result.result, "hello")

    def test_exit_code_nonzero(self):
        result = self.tool.run({"command": "false"})
        self.assertIn("Exit code:", result.result)

    def test_timeout(self):
        result = self.tool.run({"command": "sleep 10", "timeout": 100})
        self.assertIn("timed out", result.result.lower())

    def test_stderr_included(self):
        result = self.tool.run({"command": "echo out && echo err >&2"})
        self.assertIn("out", result.result)
        self.assertIn("err", result.result)
