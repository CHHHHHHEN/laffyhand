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

    # ─── diff output ───────────────────────────────────────

    def test_edit_contains_diff_in_result(self):
        f = self.root / "test.txt"
        f.write_text("foo\nbar\nbaz\n")
        tool = EditTool()
        result = asyncio.run(
            tool.run({"file_path": str(f), "old_string": "bar", "new_string": "qux"})
        )
        self.assertIn("--- ", result)
        self.assertIn("+++ ", result)
        self.assertIn("@@", result)
        self.assertIn("-bar", result)
        self.assertIn("+qux", result)

    def test_edit_replace_all_contains_diff(self):
        f = self.root / "test.txt"
        f.write_text("foo\nfoo\nfoo\n")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "old_string": "foo",
                "new_string": "bar",
                "replaceAll": True,
            })
        )
        self.assertIn("--- ", result)
        self.assertIn("+bar", result)

    def test_edit_prepend_contains_diff(self):
        f = self.root / "existing.txt"
        f.write_text("original\n")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "old_string": "",
                "new_string": "prefix",
            })
        )
        self.assertIn("--- ", result)
        self.assertIn("+prefix", result)

    def test_edit_create_has_no_diff(self):
        f = self.root / "new.txt"
        tool = EditTool()
        result = asyncio.run(
            tool.run({"file_path": str(f), "old_string": "", "new_string": "hello"})
        )
        self.assertNotIn("--- ", result)

    def test_edit_not_found_has_no_diff(self):
        f = self.root / "test.txt"
        f.write_text("hello")
        tool = EditTool()
        result = asyncio.run(
            tool.run({"file_path": str(f), "old_string": "zzz", "new_string": "xxx"})
        )
        self.assertNotIn("--- ", result)

    # ─── regex old_pattern ───────────────────────────────────────

    def test_edit_regex_pattern(self):
        f = self.root / "test.txt"
        f.write_text("foo123 bar456 baz789")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "old_pattern": r"\d+",
                "new_string": "NUM",
            })
        )
        self.assertIn("regex", result)
        self.assertIn("replaced 1", result)
        self.assertEqual(f.read_text(), "fooNUM bar456 baz789")

    def test_edit_regex_replace_all(self):
        f = self.root / "test.txt"
        f.write_text("foo123 bar456 baz789")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "old_pattern": r"\d+",
                "new_string": "NUM",
                "replaceAll": True,
            })
        )
        self.assertIn("replaced 3", result)
        self.assertEqual(f.read_text(), "fooNUM barNUM bazNUM")

    def test_edit_regex_backreference(self):
        f = self.root / "test.txt"
        f.write_text("hello world")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "old_pattern": r"(hello) (world)",
                "new_string": r"\2 \1",
            })
        )
        self.assertIn("Edited", result)
        self.assertEqual(f.read_text(), "world hello")

    def test_edit_regex_invalid_pattern(self):
        f = self.root / "test.txt"
        f.write_text("hello")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "old_pattern": r"[invalid",
                "new_string": "x",
            })
        )
        self.assertIn("Invalid regex", result)

    def test_edit_regex_no_match(self):
        f = self.root / "test.txt"
        f.write_text("hello world")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "old_pattern": r"\d+",
                "new_string": "x",
            })
        )
        self.assertIn("Pattern not found", result)

    # ─── fuzzy replaceAll ────────────────────────────────────────

    def test_edit_replace_all_fuzzy_whitespace(self):
        f = self.root / "test.txt"
        f.write_text("x y x    y")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "old_string": "x y",
                "new_string": "a b",
                "replaceAll": True,
            })
        )
        self.assertIn("replaced 2", result)
        # Both occurrences should be replaced: "x y" and "x    y"
        self.assertEqual(f.read_text(), "a b a b")

    def test_edit_replace_all_exact_still_works(self):
        f = self.root / "test.txt"
        f.write_text("foo bar foo bar foo")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "old_string": "foo",
                "new_string": "baz",
                "replaceAll": True,
            })
        )
        self.assertNotIn("fuzzy", result)
        self.assertIn("replaced 3", result)
        self.assertEqual(f.read_text(), "baz bar baz bar baz")

    # ─── multi-edit (changes array) ────────────────────────────

    def test_multi_edit_basic(self):
        f = self.root / "test.txt"
        f.write_text("foo\nbar\nbaz\n")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "changes": [
                    {"old_string": "foo", "new_string": "qux"},
                    {"old_string": "baz", "new_string": "quux"},
                ],
            })
        )
        self.assertIn("applied 2 change(s)", result)
        self.assertIn("--- ", result)
        self.assertEqual(f.read_text(), "qux\nbar\nquux\n")

    def test_multi_edit_single_change(self):
        f = self.root / "test.txt"
        f.write_text("hello world")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "changes": [
                    {"old_string": "hello", "new_string": "hi"},
                ],
            })
        )
        self.assertIn("applied 1 change(s)", result)
        self.assertEqual(f.read_text(), "hi world")

    def test_multi_edit_replace_all(self):
        f = self.root / "test.txt"
        f.write_text("x x x\ny y y\n")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "changes": [
                    {"old_string": "x", "new_string": "a", "replaceAll": True},
                    {"old_string": "y", "new_string": "b", "replaceAll": True},
                ],
            })
        )
        self.assertIn("applied 2 change(s)", result)
        self.assertEqual(f.read_text(), "a a a\nb b b\n")

    def test_multi_edit_regex_and_literal(self):
        f = self.root / "test.txt"
        f.write_text("foo123 bar456")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "changes": [
                    {"old_pattern": r"\d+", "new_string": "NUM"},
                    {"old_string": "bar", "new_string": "baz"},
                ],
            })
        )
        self.assertIn("applied 2 change(s)", result)
        self.assertEqual(f.read_text(), "fooNUM baz456")

    def test_multi_edit_chain_dependent(self):
        f = self.root / "test.txt"
        f.write_text("a")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "changes": [
                    {"old_string": "a", "new_string": "b"},
                    {"old_string": "b", "new_string": "c"},
                ],
            })
        )
        self.assertIn("applied 2 change(s)", result)
        self.assertEqual(f.read_text(), "c")

    def test_multi_edit_first_change_fails(self):
        f = self.root / "test.txt"
        f.write_text("hello world")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "changes": [
                    {"old_string": "zzz", "new_string": "xxx"},
                    {"old_string": "hello", "new_string": "hi"},
                ],
            })
        )
        self.assertIn("Change 1", result)
        self.assertIn("not found", result)
        # File should be unchanged (all-or-nothing)
        self.assertEqual(f.read_text(), "hello world")

    def test_multi_edit_second_change_fails(self):
        f = self.root / "test.txt"
        f.write_text("hello world foo")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "changes": [
                    {"old_string": "hello", "new_string": "hi"},
                    {"old_string": "zzz", "new_string": "xxx"},
                ],
            })
        )
        self.assertIn("Change 2", result)
        self.assertIn("not found", result)
        # File should be unchanged (all-or-nothing)
        self.assertEqual(f.read_text(), "hello world foo")

    def test_multi_edit_missing_new_string(self):
        f = self.root / "test.txt"
        f.write_text("hello")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "changes": [
                    {"old_string": "hello"},
                ],
            })
        )
        self.assertIn("Change 1", result)
        self.assertIn("new_string", result)

    def test_multi_edit_missing_both_old(self):
        f = self.root / "test.txt"
        f.write_text("hello")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "changes": [
                    {"new_string": "hi"},
                ],
            })
        )
        self.assertIn("Change 1", result)
        self.assertIn("old_string", result)

    def test_multi_edit_empty_changes(self):
        f = self.root / "test.txt"
        f.write_text("hello")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "changes": [],
            })
        )
        self.assertIn("No changes", result)

    def test_multi_edit_invalid_regex(self):
        f = self.root / "test.txt"
        f.write_text("hello")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "changes": [
                    {"old_pattern": r"[invalid", "new_string": "x"},
                ],
            })
        )
        self.assertIn("Change 1", result)
        self.assertIn("invalid regex", result)

    def test_multi_edit_file_not_found(self):
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(self.root / "nope.txt"),
                "changes": [
                    {"old_string": "a", "new_string": "b"},
                ],
            })
        )
        self.assertIn("not found", result.lower())

    def test_multi_edit_contains_diff(self):
        f = self.root / "test.txt"
        f.write_text("foo\nbar\nbaz\n")
        tool = EditTool()
        result = asyncio.run(
            tool.run({
                "file_path": str(f),
                "changes": [
                    {"old_string": "foo", "new_string": "qux"},
                    {"old_string": "baz", "new_string": "quux"},
                ],
            })
        )
        self.assertIn("--- ", result)
        self.assertIn("+qux", result)
        self.assertIn("+quux", result)
