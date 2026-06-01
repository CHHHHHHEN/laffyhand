import asyncio
import unittest
import tempfile
from pathlib import Path
from laffyhand.agent.tools.file.write import WriteTool


class TestWriteTool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_write_file(self):
        f = self.root / "test.txt"
        tool = WriteTool()
        result = asyncio.run(tool.run({"file_path": str(f), "content": "hello"}))
        self.assertIn("File written", result)
        self.assertEqual(f.read_text(), "hello")

    def test_write_empty_content(self):
        f = self.root / "empty.txt"
        tool = WriteTool()
        result = asyncio.run(tool.run({"file_path": str(f), "content": ""}))
        self.assertIn("File written", result)
        self.assertEqual(f.read_text(), "")

    def test_write_creates_parent_dirs(self):
        f = self.root / "sub" / "nested" / "test.txt"
        tool = WriteTool()
        result = asyncio.run(tool.run({"file_path": str(f), "content": "nested"}))
        self.assertIn("File written", result)
        self.assertTrue(f.exists())
        self.assertEqual(f.read_text(), "nested")

    def test_write_relative_path(self):
        orig_cwd = Path.cwd()
        try:
            import os

            os.chdir(self.root)
            tool = WriteTool()
            result = asyncio.run(
                tool.run({"file_path": "relative.txt", "content": "relative-path"})
            )
            self.assertIn("File written", result)
            target = self.root / "relative.txt"
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(), "relative-path")
        finally:
            import os

            os.chdir(orig_cwd)

    def test_write_line_ending_preservation_crlf(self):
        f = self.root / "crlf.txt"
        f.write_bytes(b"line1\r\nline2\r\n")
        tool = WriteTool()
        result = asyncio.run(tool.run({"file_path": str(f), "content": "new1\nnew2\n"}))
        self.assertIn("File written", result)
        raw = f.read_bytes()
        self.assertEqual(raw, b"new1\r\nnew2\r\n")

    def test_write_line_ending_preservation_lf(self):
        f = self.root / "lf.txt"
        f.write_bytes(b"line1\nline2\n")
        tool = WriteTool()
        result = asyncio.run(tool.run({"file_path": str(f), "content": "new1\nnew2\n"}))
        self.assertIn("File written", result)
        raw = f.read_bytes()
        self.assertEqual(raw, b"new1\nnew2\n")

    def test_write_blocked_env_file(self):
        f = self.root / ".env"
        tool = WriteTool()
        result = asyncio.run(tool.run({"file_path": str(f), "content": "SECRET=xxx"}))
        self.assertIn("Blocked", result)
        self.assertFalse(f.exists())

    def test_write_blocked_git_credentials(self):
        f = self.root / ".git-credentials"
        tool = WriteTool()
        result = asyncio.run(
            tool.run({"file_path": str(f), "content": "https://user:pass@host"})
        )
        self.assertIn("Blocked", result)
        self.assertFalse(f.exists())

    def test_write_diff_preview(self):
        f = self.root / "editable.txt"
        f.write_text("old content\nline2\n")
        tool = WriteTool()
        result = asyncio.run(
            tool.run({"file_path": str(f), "content": "new content\nline2\n"})
        )
        self.assertIn("File written", result)
        self.assertIn("-old content", result)
        self.assertIn("+new content", result)
        self.assertEqual(f.read_text(), "new content\nline2\n")
