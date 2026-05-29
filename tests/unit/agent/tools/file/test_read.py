import asyncio
import unittest
import tempfile
from pathlib import Path
from laffyhand.agent.tools.file.read import ReadTool


class TestReadTool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_read_file(self):
        f = self.root / "test.txt"
        f.write_text("hello world")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertEqual(result, "hello world")

    def test_read_not_found(self):
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root / "nope.txt")}))
        self.assertIn("not found", result.lower())

    def test_read_directory(self):
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root)}))
        self.assertIn("not a file", result.lower())

    def test_read_with_offset(self):
        f = self.root / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f), "offset": 2}))
        self.assertEqual(result, "line2\nline3\n")

    def test_read_with_limit(self):
        f = self.root / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f), "limit": 2}))
        self.assertEqual(result, "line1\nline2\n")

    def test_read_with_offset_and_limit(self):
        f = self.root / "test.txt"
        f.write_text("line1\nline2\nline3\nline4\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f), "offset": 2, "limit": 2}))
        self.assertEqual(result, "line2\nline3\n")
