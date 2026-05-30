import asyncio
import time
import unittest
import tempfile
from pathlib import Path

from laffyhand.agent.tools.file.read import ReadTool
from laffyhand.agent.tools.file.write import WriteTool
from laffyhand.agent.tools.file.edit import EditTool
from laffyhand.agent.tools.file.glob import GlobTool
from laffyhand.agent.tools.file.grep import GrepTool


class TestFileToolsE2E(unittest.TestCase):
    """End-to-end tests for file tools: cross-tool workflows."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    # ─── workflow: grep → read → edit ──────────────────────

    def test_grep_then_read_then_edit_workflow(self):
        src = self.root / "src"
        src.mkdir()
        (src / "main.py").write_text("import os\n\ndef main():\n    pass\n")
        (src / "utils.py").write_text("import os\n\ndef helper():\n    return 42\n")

        grep_tool = GrepTool()
        read_tool = ReadTool()
        edit_tool = EditTool()

        # Step 1: grep for "def " to find functions
        grep_result = asyncio.run(grep_tool.run({
            "pattern": r"^def ",
            "path": str(self.root),
            "include": "*.py",
        }))
        self.assertIn("main.py", grep_result)
        self.assertIn("utils.py", grep_result)

        # Step 2: read utils.py
        read_result = asyncio.run(read_tool.run({
            "file_path": str(src / "utils.py"),
        }))
        self.assertIn("helper", read_result)

        # Step 3: edit utils.py to add a new function
        time.sleep(0.02)
        edit_result = asyncio.run(edit_tool.run({
            "file_path": str(src / "utils.py"),
            "old_string": "def helper():\n    return 42",
            "new_string": "def helper():\n    return 43",
        }))
        self.assertIn("Edited", edit_result)

        # Step 4: verify the edit took effect
        verify = asyncio.run(read_tool.run({
            "file_path": str(src / "utils.py"),
        }))
        self.assertIn("return 43", verify)
        self.assertNotIn("return 42", verify)

    # ─── workflow: write → read → glob ──────────────────────

    def test_write_then_read_then_glob_workflow(self):
        write_tool = WriteTool()
        read_tool = ReadTool()
        glob_tool = GlobTool()

        # Step 1: write multiple files
        for name in ["a.py", "b.py", "c.py"]:
            asyncio.run(write_tool.run({
                "file_path": str(self.root / name),
                "content": f"# {name}\nprint('hello')\n",
            }))

        # Step 2: read one file
        read_result = asyncio.run(read_tool.run({
            "file_path": str(self.root / "a.py"),
        }))
        self.assertIn("a.py", read_result)
        self.assertIn("print", read_result)

        # Step 3: glob to find all py files
        glob_result = asyncio.run(glob_tool.run({
            "pattern": "*.py",
            "path": str(self.root),
        }))
        self.assertIn("a.py", glob_result)
        self.assertIn("b.py", glob_result)
        self.assertIn("c.py", glob_result)

    # ─── workflow: write → read (with offset/limit) → edit → verify ─

    def test_large_file_workflow(self):
        write_tool = WriteTool()
        read_tool = ReadTool()
        edit_tool = EditTool()

        lines = [f"line{i}: content" for i in range(50)]
        content = "\n".join(lines)

        # Step 1: write a larger file
        asyncio.run(write_tool.run({
            "file_path": str(self.root / "large.txt"),
            "content": content,
        }))

        # Step 2: read with offset and limit
        read_result = asyncio.run(read_tool.run({
            "file_path": str(self.root / "large.txt"),
            "offset": 5,
            "limit": 3,
        }))
        self.assertIn("5|line4", read_result)
        self.assertIn("6|line5", read_result)
        self.assertIn("7|line6", read_result)
        self.assertNotIn("4|line3", read_result)
        self.assertNotIn("8|line7", read_result)

        # Step 3: edit a line
        edit_result = asyncio.run(edit_tool.run({
            "file_path": str(self.root / "large.txt"),
            "old_string": "line10",
            "new_string": "line10: modified",
        }))
        self.assertIn("Edited", edit_result)

        # Step 4: verify
        verify = asyncio.run(read_tool.run({
            "file_path": str(self.root / "large.txt"),
            "offset": 11,
            "limit": 1,
        }))
        self.assertIn("modified", verify)

    # ─── workflow: blocked path across tools ────────────────

    def test_blocked_path_consistency(self):
        write_tool = WriteTool()
        edit_tool = EditTool()

        # Both WriteTool and EditTool should block .env
        write_result = asyncio.run(write_tool.run({
            "file_path": str(self.root / ".env"),
            "content": "SECRET=xxx",
        }))
        self.assertIn("Blocked", write_result)

        edit_result = asyncio.run(edit_tool.run({
            "file_path": str(self.root / "some" / ".." / ".env"),
            "old_string": "",
            "new_string": "SECRET=xxx",
        }))
        self.assertIn("Blocked", edit_result)

    # ─── workflow: glob with ripgrep fallback ───────────────

    def test_glob_no_match_clean_message(self):
        glob_tool = GlobTool()
        result = asyncio.run(glob_tool.run({
            "pattern": "*.nonexistent",
            "path": str(self.root),
        }))
        self.assertIn("No files found", result)

    # ─── workflow: grep with all output modes ───────────────

    def test_grep_all_output_modes(self):
        (self.root / "data.py").write_text("target\nfoo\ntarget\nbar\ntarget\n")
        grep_tool = GrepTool()

        # content mode
        content_result = asyncio.run(grep_tool.run({
            "pattern": "target",
            "path": str(self.root),
            "output_mode": "content",
        }))
        self.assertIn("target", content_result)

        # files_only mode
        files_result = asyncio.run(grep_tool.run({
            "pattern": "target",
            "path": str(self.root),
            "output_mode": "files_only",
        }))
        self.assertIn("data.py", files_result)

        # count mode
        count_result = asyncio.run(grep_tool.run({
            "pattern": "target",
            "path": str(self.root),
            "output_mode": "count",
        }))
        self.assertIn("3", count_result)

    # ─── workflow: write with line ending preservation ──────

    def test_write_line_ending_preserved_across_edit(self):
        write_tool = WriteTool()

        # Write with CRLF
        asyncio.run(write_tool.run({
            "file_path": str(self.root / "crlf.txt"),
            "content": "line1\nline2\n",
        }))

        # Verify CRLF content
        raw = (self.root / "crlf.txt").read_bytes()
        self.assertEqual(raw, b"line1\nline2\n")

        # Now edit it
        edit_tool = EditTool()
        asyncio.run(edit_tool.run({
            "file_path": str(self.root / "crlf.txt"),
            "old_string": "line1",
            "new_string": "modified",
        }))

        # Verify line ending preserved (LF)
        raw_after = (self.root / "crlf.txt").read_bytes()
        self.assertEqual(raw_after, b"modified\nline2\n")
