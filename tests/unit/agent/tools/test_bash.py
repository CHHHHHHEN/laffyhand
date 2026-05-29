import tempfile
import unittest
from pathlib import Path

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

    def test_workdir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.tool.run({"command": "pwd", "workdir": tmpdir})
            self.assertEqual(result.result.strip(), tmpdir)

    def test_workdir_affects_file_operations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "marker.txt").touch()
            result = self.tool.run({"command": "ls marker.txt", "workdir": tmpdir})
            self.assertIn("marker.txt", result.result)
