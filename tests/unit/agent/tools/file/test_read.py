import asyncio
import time
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

    # ─── basic file reading ─────────────────────────────────

    def test_read_file(self):
        f = self.root / "test.txt"
        f.write_text("hello world")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertIn("1|hello world", result)

    def test_read_empty_file(self):
        f = self.root / "empty.txt"
        f.write_text("")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertEqual(result, "")

    def test_read_with_offset(self):
        f = self.root / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f), "offset": 2}))
        self.assertIn("2|line2", result)
        self.assertNotIn("1|line1", result)

    def test_read_with_limit(self):
        f = self.root / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f), "limit": 2}))
        self.assertIn("1|line1", result)
        self.assertIn("2|line2", result)
        self.assertNotIn("3|line3", result)

    def test_read_with_offset_and_limit(self):
        f = self.root / "test.txt"
        f.write_text("line1\nline2\nline3\nline4\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f), "offset": 2, "limit": 2}))
        self.assertIn("2|line2", result)
        self.assertIn("3|line3", result)
        self.assertNotIn("1|line1", result)

    def test_read_out_of_range(self):
        f = self.root / "test.txt"
        f.write_text("line1\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f), "offset": 10}))
        self.assertIn("out of range", result.lower())

    # ─── file not found ──────────────────────────────────────

    def test_read_not_found(self):
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root / "nope.txt")}))
        self.assertIn("not found", result.lower())

    def test_read_not_found_with_suggestion(self):
        """Should suggest similar files when the exact name is not found."""
        (self.root / "readme.md").write_text("hello")
        (self.root / "readme.txt").write_text("hello")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root / "readme.rst")}))
        self.assertIn("Did you mean", result)

    # ─── directory listing ──────────────────────────────────

    def test_read_directory(self):
        (self.root / "a.py").touch()
        (self.root / "sub").mkdir()
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root)}))
        self.assertIn("Contents of", result)
        self.assertIn("a.py", result)
        self.assertIn("sub/", result)

    def test_read_directory_shows_line_count(self):
        (self.root / "a.py").write_text("line1\nline2\n")
        (self.root / "empty.txt").touch()
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root)}))
        self.assertIn("a.py (2 lines)", result)
        self.assertIn("empty.txt (0 lines)", result)

    def test_read_directory_with_limit(self):
        for i in range(5):
            (self.root / f"f{i}.py").touch()
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root), "limit": 2}))
        lines = result.strip().split("\n")
        # header + 2 entries
        self.assertEqual(len(lines), 3)

    # ─── directory depth control ────────────────────────────

    def test_read_directory_depth_1_is_flat(self):
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("content\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root), "depth": 1}))
        self.assertIn("sub/", result)
        self.assertNotIn("deep.txt", result)

    def test_read_directory_depth_2_shows_nested_files(self):
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("content\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root), "depth": 2}))
        self.assertIn("sub/", result)
        self.assertIn("deep.txt", result)

    def test_read_directory_depth_2_stops_after_2_levels(self):
        a = self.root / "a"
        b = a / "b"
        c = b / "c"
        a.mkdir()
        b.mkdir()
        c.mkdir()
        (c / "leaf.txt").write_text("deep\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root), "depth": 2}))
        self.assertIn("a/", result)
        self.assertIn("b/", result)
        self.assertNotIn("c/", result)
        self.assertNotIn("leaf.txt", result)

    def test_read_directory_depth_3_reaches_third_level(self):
        a = self.root / "a"
        b = a / "b"
        c = b / "c"
        a.mkdir()
        b.mkdir()
        c.mkdir()
        (c / "leaf.txt").write_text("deep\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root), "depth": 3}))
        self.assertIn("a/", result)
        self.assertIn("b/", result)
        self.assertIn("c/", result)
        self.assertNotIn("leaf.txt", result)

    def test_read_directory_depth_4_reaches_files(self):
        a = self.root / "a"
        b = a / "b"
        c = b / "c"
        a.mkdir()
        b.mkdir()
        c.mkdir()
        (c / "leaf.txt").write_text("deep\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root), "depth": 4}))
        self.assertIn("leaf.txt", result)

    def test_read_directory_depth_0_returns_empty(self):
        (self.root / "x.py").touch()
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root), "depth": 0}))
        self.assertEqual(result, "")

    def test_read_directory_depth_defaults_to_2(self):
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "inner.txt").write_text("content\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root)}))
        self.assertIn("sub/", result)
        self.assertIn("inner.txt", result)

    def test_read_directory_depth_shows_line_count_in_nested_files(self):
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "code.py").write_text("a\nb\nc\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root), "depth": 2}))
        self.assertIn("code.py (3 lines)", result)

    def test_read_batch_with_depth(self):
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("data\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"paths": [str(self.root)], "depth": 2}))
        self.assertIn("sub/", result)
        self.assertIn("nested.txt", result)

    def test_read_directory_depth_uses_indentation(self):
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "inner.txt").write_text("data\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root), "depth": 2}))
        # nested file should be preceded by whitespace
        for line in result.splitlines():
            if "inner.txt" in line:
                self.assertTrue(line.startswith("    "), f"Expected indentation: {line!r}")

    # ─── directory listing binary/file format ─────────────

    def test_read_directory_shows_binary_files_without_trailing_slash(self):
        """Binary files in directory listing show as (binary), not as dirs with /."""
        (self.root / "data.zip").write_text("fake zip")
        (self.root / "lib.so").write_text("fake so")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root), "depth": 1}))
        self.assertIn("data.zip (binary)", result)
        self.assertIn("lib.so (binary)", result)
        self.assertNotIn("data.zip/", result)
        self.assertNotIn("lib.so/", result)

    def test_read_directory_binary_files_in_subdir(self):
        """Binary files nested in subdirectories show as (binary)."""
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "data.zip").write_text("fake")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root), "depth": 2}))
        self.assertIn("data.zip (binary)", result)
        self.assertIn("sub/", result)

    def test_read_directory_conflit_file_and_dir_separated(self):
        """Directories get / suffix, text files get line count, binary files get (binary)."""
        (self.root / "readme.txt").write_text("hello")
        (self.root / "data.zip").write_text("fake")
        (self.root / "sub").mkdir()
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root), "depth": 1}))
        self.assertIn("readme.txt (", result)   # text file has line count
        self.assertIn("data.zip (binary)", result)  # binary file marked
        self.assertIn("sub/", result)              # dir has trailing /

    # ─── binary detection ───────────────────────────────────

    def test_read_binary_by_extension(self):
        f = self.root / "data.zip"
        f.write_text("not actually zip")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertIn("binary", result.lower())

    def test_read_binary_by_content(self):
        f = self.root / "data.bin"
        f.write_bytes(b"\x00\x01\x02\x03")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertIn("binary", result.lower())

    # ─── line truncation ────────────────────────────────────

    def test_long_line_truncation(self):
        long = "x" * 3000 + "\n"
        f = self.root / "long.txt"
        f.write_text(long)
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertIn("truncated", result.lower())
        self.assertLess(len(result), 2100)

    # ─── offset validation ─────────────────────────────────

    def test_read_invalid_offset(self):
        f = self.root / "test.txt"
        f.write_text("line1\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f), "offset": 0}))
        self.assertIn("invalid offset", result.lower())

    # ─── dedup / consecutive read guard ────────────────────

    def test_identical_read_returns_unchanged(self):
        f = self.root / "dedup.txt"
        f.write_text("hello")
        tool = ReadTool()
        r1 = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertIn("1|hello", r1)
        r2 = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertIn("unchanged", r2.lower())

    def test_consecutive_count_resets_on_interleaved_read(self):
        f = self.root / "a.txt"
        f2 = self.root / "b.txt"
        f.write_text("AAA")
        f2.write_text("BBB")
        tool = ReadTool()
        asyncio.run(tool.run({"file_path": str(f)}))
        asyncio.run(tool.run({"file_path": str(f2)}))
        r = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertIn("unchanged", r.lower())

    def test_file_change_returns_new_content(self):
        f = self.root / "dedup.txt"
        f.write_text("hello")
        tool = ReadTool()
        asyncio.run(tool.run({"file_path": str(f)}))
        time.sleep(0.02)
        f.write_text("world")
        r = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertIn("1|world", r)

    def test_consecutive_reads_eventually_blocked(self):
        f = self.root / "loop.txt"
        f.write_text("data")
        tool = ReadTool()
        for _ in range(5):
            r = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertIn("consecutively", r.lower())
        self.assertIn("different approach", r.lower())

    # ─── large file warning ────────────────────────────────

    def test_read_large_file_warning(self):
        chunk = "x" * 1024 * 100
        content = (chunk + "\n") * 6
        f = self.root / "large.txt"
        f.write_text(content)
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertIn("File is large", result)

    # ─── directory offset validation ──────────────────────

    def test_read_directory_offset_out_of_range(self):
        tool = ReadTool()
        result = asyncio.run(
            tool.run(
                {
                    "file_path": str(self.root),
                    "offset": 100,
                }
            )
        )
        self.assertIn("out of range", result.lower())

    # ─── pattern-based context reading ─────────────────────

    def test_read_with_pattern(self):
        f = self.root / "test.py"
        f.write_text("pre\ndef foo():\n    pass\n\nmid\ndef bar():\n    pass\npost\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f), "pattern": "def"}))
        self.assertIn("2>def foo():", result)
        self.assertIn("6>def bar():", result)

    def test_read_with_pattern_and_context(self):
        f = self.root / "test.py"
        f.write_text("a\nb\ndef foo():\n    pass\ne\nf\n")
        tool = ReadTool()
        result = asyncio.run(
            tool.run({"file_path": str(f), "pattern": "def", "context": 1})
        )
        self.assertIn("2 ", result)  # context line before first match
        self.assertIn("3>def foo():", result)
        self.assertIn("4 ", result)  # context line after first match

    def test_read_with_pattern_and_offset_limit(self):
        f = self.root / "test.py"
        f.write_text(
            "aaa\nbbb\ndef a():\n    pass\nccc\nddd\ndef b():\n    pass\neee\nfff\ndef c():\n    pass\nggg\n"
        )
        tool = ReadTool()
        result = asyncio.run(
            tool.run(
                {
                    "file_path": str(f),
                    "pattern": "def",
                    "offset": 1,
                    "limit": 1,
                    "context": 0,
                }
            )
        )
        self.assertNotIn("def a():", result)
        self.assertIn("def b():", result)
        self.assertNotIn("def c():", result)

    def test_read_with_pattern_no_match(self):
        f = self.root / "test.txt"
        f.write_text("hello world\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f), "pattern": "nope"}))
        self.assertIn("No matches", result)

    def test_read_with_pattern_invalid_regex(self):
        f = self.root / "test.txt"
        f.write_text("hello\n")
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(f), "pattern": "["}))
        self.assertIn("Invalid regex", result)

    def test_read_with_pattern_separator(self):
        content = "a\nb\nMATCH1\nc\nd\nb\nMATCH2\nc\nd\n"
        f = self.root / "test.txt"
        f.write_text(content)
        tool = ReadTool()
        result = asyncio.run(
            tool.run({"file_path": str(f), "pattern": "MATCH", "context": 0})
        )
        self.assertIn("--\n", result)

    # ─── batch reading ─────────────────────────────────────

    def test_read_batch_multiple_files(self):
        (self.root / "a.txt").write_text("alpha\n")
        (self.root / "b.txt").write_text("beta\n")
        tool = ReadTool()
        result = asyncio.run(
            tool.run(
                {
                    "paths": [str(self.root / "a.txt"), str(self.root / "b.txt")],
                }
            )
        )
        self.assertIn("a.txt", result)
        self.assertIn("b.txt", result)
        self.assertIn("1|alpha", result)
        self.assertIn("1|beta", result)

    def test_read_batch_with_pattern(self):
        (self.root / "a.txt").write_text("foo\nbar\nbaz\n")
        (self.root / "b.txt").write_text("bar\nqux\nfoo\n")
        tool = ReadTool()
        result = asyncio.run(
            tool.run(
                {
                    "paths": [str(self.root / "a.txt"), str(self.root / "b.txt")],
                    "pattern": "foo",
                    "context": 0,
                }
            )
        )
        self.assertIn("1>foo", result)
        self.assertIn("3>foo", result)

    def test_read_batch_missing_file(self):
        (self.root / "a.txt").write_text("alpha\n")
        tool = ReadTool()
        result = asyncio.run(
            tool.run(
                {
                    "paths": [str(self.root / "a.txt"), str(self.root / "nope.txt")],
                }
            )
        )
        self.assertIn("alpha", result)
        self.assertIn("not found", result.lower())

    def test_read_batch_requires_paths_or_file_path(self):
        tool = ReadTool()
        result = asyncio.run(tool.run({}))
        self.assertIn("required", result.lower())

    # ─── preference resolver integration ──────────────────

    def test_read_with_preference_resolver(self):
        """resolve_preferences instructions are prepended to the result."""
        f = self.root / "test.py"
        f.write_text("code = 1\n")

        def resolver(file_path, claim_id):
            return [
                {
                    "filepath": "/fake/AGENTS.md",
                    "content": "Instructions from: /fake/AGENTS.md\nUse Python",
                }
            ]

        tool = ReadTool(preference_resolver=resolver)
        result = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertIn("Instructions from: /fake/AGENTS.md", result)
        self.assertIn("Use Python", result)
        self.assertIn("1|code = 1", result)

    def test_read_with_resolver_no_instructions(self):
        """When resolver returns empty list, no injection occurs."""
        f = self.root / "test.py"
        f.write_text("code = 1\n")

        def resolver(file_path, claim_id):
            return []

        tool = ReadTool(preference_resolver=resolver)
        result = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertIn("1|code = 1", result)
        self.assertNotIn("<preference>", result)

    def test_read_with_resolver_passes_claim_id(self):
        """The claim_id (from _claim_id or session_id param) is passed to resolver."""
        f = self.root / "test.py"
        f.write_text("code = 1\n")

        captured = []

        def resolver(file_path, claim_id):
            captured.append(claim_id)
            return []

        tool = ReadTool(preference_resolver=resolver)
        asyncio.run(
            tool.run({"file_path": str(f), "_claim_id": "test-claim"})
        )
        self.assertEqual(captured, ["test-claim"])

    def test_read_binary_skips_resolver(self):
        """Binary files skip the preference resolver."""
        f = self.root / "data.bin"
        f.write_bytes(b"\x00\x01\x02\x03")

        resolver_called = False

        def resolver(file_path, claim_id):
            nonlocal resolver_called
            resolver_called = True
            return []

        tool = ReadTool(preference_resolver=resolver)
        result = asyncio.run(tool.run({"file_path": str(f)}))
        self.assertIn("binary", result.lower())
        self.assertFalse(resolver_called)
