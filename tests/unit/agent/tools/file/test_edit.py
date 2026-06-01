import asyncio
import unittest
import tempfile
from pathlib import Path
from laffyhand.agent.tools.file.edit import EditTool


class TestEditTool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_edit_single_occurrence(self):
        f = self.root / "test.txt"
        f.write_text("foo\nbar\nbaz")
        tool = EditTool()
        result = asyncio.run(
            tool.run({"file_path": str(f), "old_string": "bar", "new_string": "qux"})
        )
        self.assertIn("Edited", result)
        self.assertEqual(f.read_text(), "foo\nqux\nbaz")

    def test_edit_file_not_found(self):
        tool = EditTool()
        result = asyncio.run(
            tool.run(
                {
                    "file_path": str(self.root / "nope.txt"),
                    "old_string": "a",
                    "new_string": "b",
                }
            )
        )
        self.assertIn("not found", result.lower())

    def test_edit_string_not_found(self):
        f = self.root / "test.txt"
        f.write_text("hello")
        tool = EditTool()
        result = asyncio.run(
            tool.run({"file_path": str(f), "old_string": "zzz", "new_string": "xxx"})
        )
        self.assertIn("not found", result)

    def test_edit_multiple_matches_no_replace_all(self):
        f = self.root / "test.txt"
        f.write_text("foo\nfoo\nfoo")
        tool = EditTool()
        result = asyncio.run(
            tool.run({"file_path": str(f), "old_string": "foo", "new_string": "bar"})
        )
        self.assertIn("Edited", result)
        self.assertEqual(f.read_text(), "bar\nfoo\nfoo")

    def test_edit_replace_all(self):
        f = self.root / "test.txt"
        f.write_text("foo\nfoo\nfoo")
        tool = EditTool()
        result = asyncio.run(
            tool.run(
                {
                    "file_path": str(f),
                    "old_string": "foo",
                    "new_string": "bar",
                    "replaceAll": True,
                }
            )
        )
        self.assertIn("3", result)
        self.assertEqual(f.read_text(), "bar\nbar\nbar")

    def test_edit_old_string_empty_creates_file(self):
        f = self.root / "new.txt"
        tool = EditTool()
        result = asyncio.run(
            tool.run(
                {
                    "file_path": str(f),
                    "old_string": "",
                    "new_string": "hello",
                }
            )
        )
        self.assertIn("Created", result)
        self.assertEqual(f.read_text(), "hello")

    def test_edit_old_string_empty_prepends(self):
        f = self.root / "existing.txt"
        f.write_text("original")
        tool = EditTool()
        result = asyncio.run(
            tool.run(
                {
                    "file_path": str(f),
                    "old_string": "",
                    "new_string": "prefix",
                }
            )
        )
        self.assertIn("Edited", result)
        self.assertEqual(f.read_text(), "prefix\noriginal")

    def test_edit_whitespace_normalized_match(self):
        f = self.root / "test.txt"
        f.write_text("def foo():\n    print('hello')\n")
        tool = EditTool()
        result = asyncio.run(
            tool.run(
                {
                    "file_path": str(f),
                    "old_string": "def foo():\n    print('hello')",
                    "new_string": "def foo():\n    print('world')",
                }
            )
        )
        self.assertIn("Edited", result)
        self.assertEqual(f.read_text(), "def foo():\n    print('world')\n")

    def test_edit_blocked_path(self):
        f = self.root / ".env"
        f.write_text("OLD=val")
        tool = EditTool()
        result = asyncio.run(
            tool.run(
                {
                    "file_path": str(f),
                    "old_string": "OLD=val",
                    "new_string": "NEW=val",
                }
            )
        )
        self.assertIn("Blocked", result)

    def test_edit_line_ending_preservation(self):
        f = self.root / "crlf.txt"
        f.write_bytes(b"foo\r\nbar\r\n")
        tool = EditTool()
        result = asyncio.run(
            tool.run(
                {
                    "file_path": str(f),
                    "old_string": "foo",
                    "new_string": "baz",
                }
            )
        )
        self.assertIn("Edited", result)
        raw = f.read_bytes()
        self.assertEqual(raw, b"baz\r\nbar\r\n")

    def test_edit_escape_normalized_match(self):
        f = self.root / "test.txt"
        f.write_text("hello\nworld")
        tool = EditTool()
        result = asyncio.run(
            tool.run(
                {
                    "file_path": str(f),
                    "old_string": "hello\\nworld",
                    "new_string": "hello\nWORLD",
                }
            )
        )
        self.assertIn("escape normalized", result)
        self.assertEqual(f.read_text(), "hello\nWORLD")

    def test_edit_trimmed_boundary_match(self):
        f = self.root / "test.txt"
        f.write_text("hello\nworld\n")
        tool = EditTool()
        result = asyncio.run(
            tool.run(
                {
                    "file_path": str(f),
                    "old_string": "  hello\nworld  ",
                    "new_string": "hi\nworld",
                }
            )
        )
        self.assertIn("trimmed boundary", result)
        self.assertEqual(f.read_text(), "hi\nworld\n")

    def test_edit_directory_rejected(self):
        tool = EditTool()
        result = asyncio.run(
            tool.run(
                {
                    "file_path": str(self.root),
                    "old_string": "x",
                    "new_string": "y",
                }
            )
        )
        self.assertIn("Cannot edit a directory", result)

    def test_edit_relative_path_resolved(self):
        orig_cwd = Path.cwd()
        try:
            import os

            os.chdir(self.root)
            f = self.root / "target.txt"
            f.write_text("content")
            tool = EditTool()
            result = asyncio.run(
                tool.run(
                    {
                        "file_path": "target.txt",
                        "old_string": "content",
                        "new_string": "modified",
                    }
                )
            )
            self.assertIn("Edited", result)
            self.assertEqual(f.read_text(), "modified")
        finally:
            import os

            os.chdir(orig_cwd)
