import asyncio
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
        result = asyncio.run(tool.run({"pattern": "foo", "path": str(self.root), "include": "*.py"}))
        self.assertIn("foo", result)
        self.assertIn("test.py", result)

    def test_grep_no_match(self):
        (self.root / "test.py").write_text("hello world")
        tool = GrepTool()
        result = asyncio.run(tool.run({"pattern": "zzz", "path": str(self.root), "include": "*.py"}))
        self.assertIn("No matches", result)

    def test_grep_regex(self):
        (self.root / "test.py").write_text("abc123\ndef456\n")
        tool = GrepTool()
        result = asyncio.run(tool.run({"pattern": r"\d+", "path": str(self.root), "include": "*.py"}))
        self.assertIn("abc123", result)
        self.assertIn("def456", result)

    def test_grep_files_only(self):
        (self.root / "a.py").write_text("match")
        (self.root / "b.txt").write_text("match")
        (self.root / "c.py").write_text("no")
        tool = GrepTool()
        result = asyncio.run(tool.run({
            "pattern": "match", "path": str(self.root),
            "output_mode": "files_only",
        }))
        self.assertIn("a.py", result)
        self.assertIn("b.txt", result)

    def test_grep_limit(self):
        (self.root / "test.py").write_text("\n".join(f"line{i}" for i in range(20)))
        tool = GrepTool()
        result = asyncio.run(tool.run({
            "pattern": "line", "path": str(self.root),
            "include": "*.py", "limit": 5,
        }))
        lines = result.strip().split("\n")
        self.assertLessEqual(len(lines), 6)  # 5 matches + optional footer

    def test_grep_single_file(self):
        f = self.root / "target.py"
        f.write_text("hello\nworld\n")
        tool = GrepTool()
        result = asyncio.run(tool.run({"pattern": "world", "path": str(f)}))
        self.assertIn("world", result)

    def test_grep_invalid_regex(self):
        tool = GrepTool()
        result = asyncio.run(tool.run({"pattern": r"[invalid", "path": str(self.root)}))
        self.assertIn("Invalid regex", result)
