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

    def test_read_directory_with_limit(self):
        for i in range(5):
            (self.root / f"f{i}.py").touch()
        tool = ReadTool()
        result = asyncio.run(tool.run({"file_path": str(self.root), "limit": 2}))
        lines = result.strip().split("\n")
        # header + 2 entries
        self.assertEqual(len(lines), 3)

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
