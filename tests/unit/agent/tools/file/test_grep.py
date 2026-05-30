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

    def test_grep_context_before(self):
        (self.root / "test.py").write_text("a\nb\nc\nmatch\nd\n")
        tool = GrepTool()
        result = asyncio.run(tool.run({
            "pattern": "match", "path": str(self.root),
            "include": "*.py", "context": 2,
        }))
        self.assertIn("match", result)
        self.assertIn("b", result)
        self.assertIn("c", result)

    def test_grep_context_after(self):
        (self.root / "test.py").write_text("match\na\nb\nc\nd\n")
        tool = GrepTool()
        result = asyncio.run(tool.run({
            "pattern": "match", "path": str(self.root),
            "include": "*.py", "context": 3,
        }))
        self.assertIn("match", result)
        self.assertIn("a", result)
        self.assertIn("c", result)

    def test_grep_offset(self):
        (self.root / "test.py").write_text("\n".join(f"line{i}" for i in range(20)))
        tool = GrepTool()
        result = asyncio.run(tool.run({
            "pattern": r"line\d", "path": str(self.root),
            "include": "*.py", "offset": 10,
        }))
        self.assertNotIn("line0", result)
        self.assertIn("line10", result)

    def test_grep_count_mode(self):
        (self.root / "a.py").write_text("match\nmatch\n")
        (self.root / "b.py").write_text("match")
        tool = GrepTool()
        result = asyncio.run(tool.run({
            "pattern": "match", "path": str(self.root),
            "output_mode": "count",
        }))
        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 2)
        self.assertIn("2", lines[0])
        self.assertIn("1", lines[1])
