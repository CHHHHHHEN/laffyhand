import asyncio
import unittest
import tempfile
from pathlib import Path
from laffyhand.agent.tools.file.list_dir import ListDirTool


class TestListDirTool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    # ─── basic directory listing ────────────────────────────

    def test_list_dir_directory(self):
        (self.root / "a.py").touch()
        (self.root / "sub").mkdir()
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root)}))
        self.assertIn("Contents of", result)
        self.assertIn("a.py", result)
        self.assertIn("sub/", result)

    def test_list_dir_shows_line_count(self):
        (self.root / "a.py").write_text("line1\nline2\n")
        (self.root / "empty.txt").touch()
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root)}))
        self.assertIn("a.py (2 lines)", result)
        self.assertIn("empty.txt (0 lines)", result)

    def test_list_dir_with_limit(self):
        for i in range(5):
            (self.root / f"f{i}.py").touch()
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root), "limit": 2}))
        lines = result.strip().split("\n")
        # header + 2 entries
        self.assertEqual(len(lines), 3)

    # ─── directory depth control ────────────────────────────

    def test_list_dir_depth_1_is_flat(self):
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("content\n")
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root), "depth": 1}))
        self.assertIn("sub/", result)
        self.assertNotIn("deep.txt", result)

    def test_list_dir_depth_2_shows_nested_files(self):
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("content\n")
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root), "depth": 2}))
        self.assertIn("sub/", result)
        self.assertIn("deep.txt", result)

    def test_list_dir_depth_2_stops_after_2_levels(self):
        a = self.root / "a"
        b = a / "b"
        c = b / "c"
        a.mkdir()
        b.mkdir()
        c.mkdir()
        (c / "leaf.txt").write_text("deep\n")
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root), "depth": 2}))
        self.assertIn("a/", result)
        self.assertIn("b/", result)
        self.assertNotIn("c/", result)
        self.assertNotIn("leaf.txt", result)

    def test_list_dir_depth_3_reaches_third_level(self):
        a = self.root / "a"
        b = a / "b"
        c = b / "c"
        a.mkdir()
        b.mkdir()
        c.mkdir()
        (c / "leaf.txt").write_text("deep\n")
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root), "depth": 3}))
        self.assertIn("a/", result)
        self.assertIn("b/", result)
        self.assertIn("c/", result)
        self.assertNotIn("leaf.txt", result)

    def test_list_dir_depth_4_reaches_files(self):
        a = self.root / "a"
        b = a / "b"
        c = b / "c"
        a.mkdir()
        b.mkdir()
        c.mkdir()
        (c / "leaf.txt").write_text("deep\n")
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root), "depth": 4}))
        self.assertIn("leaf.txt", result)

    def test_list_dir_depth_0_returns_empty(self):
        (self.root / "x.py").touch()
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root), "depth": 0}))
        self.assertEqual(result, "")

    def test_list_dir_depth_defaults_to_2(self):
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "inner.txt").write_text("content\n")
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root)}))
        self.assertIn("sub/", result)
        self.assertIn("inner.txt", result)

    def test_list_dir_depth_shows_line_count_in_nested_files(self):
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "code.py").write_text("a\nb\nc\n")
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root), "depth": 2}))
        self.assertIn("code.py (3 lines)", result)

    def test_list_dir_depth_uses_indentation(self):
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "inner.txt").write_text("data\n")
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root), "depth": 2}))
        # nested file should be preceded by whitespace
        for line in result.splitlines():
            if "inner.txt" in line:
                self.assertTrue(line.startswith("    "), f"Expected indentation: {line!r}")

    # ─── directory listing binary/file format ─────────────

    def test_list_dir_shows_binary_files_without_trailing_slash(self):
        """Binary files in directory listing show as (binary), not as dirs with /."""
        (self.root / "data.zip").write_text("fake zip")
        (self.root / "lib.so").write_text("fake so")
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root), "depth": 1}))
        self.assertIn("data.zip (binary)", result)
        self.assertIn("lib.so (binary)", result)
        self.assertNotIn("data.zip/", result)
        self.assertNotIn("lib.so/", result)

    def test_list_dir_binary_files_in_subdir(self):
        """Binary files nested in subdirectories show as (binary)."""
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "data.zip").write_text("fake")
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root), "depth": 2}))
        self.assertIn("data.zip (binary)", result)
        self.assertIn("sub/", result)

    def test_list_dir_conflit_file_and_dir_separated(self):
        """Directories get / suffix, text files get line count, binary files get (binary)."""
        (self.root / "readme.txt").write_text("hello")
        (self.root / "data.zip").write_text("fake")
        (self.root / "sub").mkdir()
        tool = ListDirTool()
        result = asyncio.run(tool.run({"directory_path": str(self.root), "depth": 1}))
        self.assertIn("readme.txt (", result)     # text file has line count
        self.assertIn("data.zip (binary)", result)  # binary file marked
        self.assertIn("sub/", result)               # dir has trailing /

    # ─── offset validation ─────────────────────────────

    def test_list_dir_offset_out_of_range(self):
        tool = ListDirTool()
        result = asyncio.run(
            tool.run(
                {
                    "directory_path": str(self.root),
                    "offset": 100,
                }
            )
        )
        self.assertIn("out of range", result.lower())

    # ─── error cases ──────────────────────────────────────

    def test_list_dir_not_found(self):
        tool = ListDirTool()
        result = asyncio.run(
            tool.run({"directory_path": str(self.root / "nope")})
        )
        self.assertIn("not found", result.lower())

    def test_list_dir_on_file(self):
        f = self.root / "test.txt"
        f.write_text("hello")
        tool = ListDirTool()
        result = asyncio.run(
            tool.run({"directory_path": str(f)})
        )
        self.assertIn("not a directory", result.lower())
        self.assertIn("read tool", result.lower())

    def test_list_dir_requires_directory_path(self):
        tool = ListDirTool()
        result = asyncio.run(tool.run({}))
        self.assertIn("required", result.lower())
