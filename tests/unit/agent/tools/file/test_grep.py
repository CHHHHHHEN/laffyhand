import unittest
import tempfile
from pathlib import Path
from laffyhand.agent.tools.file.grep import GrepTool


class TestGrepTool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_grep_match(self):
        (self.root / "test.py").write_text("line1\nfoo\nline3")
        tool = GrepTool()
        result = tool.run({"pattern": "foo", "path": str(self.root), "include": "*.py"})
        self.assertIn("foo", result)
        self.assertIn("test.py", result)

    def test_grep_no_match(self):
        (self.root / "test.py").write_text("hello world")
        tool = GrepTool()
        result = tool.run({"pattern": "zzz", "path": str(self.root), "include": "*.py"})
        self.assertIn("No matches", result)

    def test_grep_regex(self):
        (self.root / "test.py").write_text("abc123\ndef456\n")
        tool = GrepTool()
        result = tool.run({"pattern": r"\d+", "path": str(self.root), "include": "*.py"})
        self.assertIn("abc123", result)
        self.assertIn("def456", result)
