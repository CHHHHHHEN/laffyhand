import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import laffyhand.core.tools.file._ripgrep as _rg

from laffyhand.core.tools.file._ripgrep import (
    _rg_cmd,
    glob,
    grep,
    grep_count,
    grep_files,
    rg_available,
)


class TestRgAvailable(unittest.TestCase):
    @patch("laffyhand.core.tools.file._ripgrep.shutil.which", return_value="/usr/bin/rg")
    def test_available(self, mock_which):
        _rg._RG_CACHE = None
        self.assertTrue(rg_available())

    @patch("laffyhand.core.tools.file._ripgrep.shutil.which", return_value=None)
    def test_not_available(self, mock_which):
        _rg._RG_CACHE = None
        self.assertFalse(rg_available())


class TestRgCmd(unittest.TestCase):
    def test_basic(self):
        cmd = _rg_cmd("--foo", "bar")
        self.assertEqual(cmd, ["rg", "--foo", "bar", "."])

    def test_with_include(self):
        cmd = _rg_cmd("--foo", include="*.py")
        self.assertEqual(cmd, ["rg", "--foo", "--glob", "*.py", "."])

    def test_no_include(self):
        cmd = _rg_cmd("--foo", include=None)
        self.assertEqual(cmd, ["rg", "--foo", "."])


class TestGlob(unittest.IsolatedAsyncioTestCase):
    async def test_success(self):
        with patch("laffyhand.core.tools.file._ripgrep._rg_run", new_callable=AsyncMock) as mock:
            mock.return_value = "a.py\nb.py\n"
            result = await glob(Path("/cwd"), "*.py")
            self.assertEqual(result, ["a.py", "b.py"])

    async def test_no_match(self):
        with patch("laffyhand.core.tools.file._ripgrep._rg_run", new_callable=AsyncMock) as mock:
            mock.return_value = ""
            result = await glob(Path("/cwd"), "*.py")
            self.assertEqual(result, [])

    async def test_failure_returns_none(self):
        with patch("laffyhand.core.tools.file._ripgrep._rg_run", new_callable=AsyncMock) as mock:
            mock.return_value = None
            result = await glob(Path("/cwd"), "*.py")
            self.assertIsNone(result)

    async def test_shorter_timeout(self):
        with patch("laffyhand.core.tools.file._ripgrep._rg_run", new_callable=AsyncMock) as mock:
            mock.return_value = None
            await glob(Path("/cwd"), "*.py")
            self.assertEqual(mock.call_args[1]["timeout"], 30)


class TestGrep(unittest.IsolatedAsyncioTestCase):
    async def test_success(self):
        with patch("laffyhand.core.tools.file._ripgrep._rg_run", new_callable=AsyncMock) as mock:
            mock.return_value = "a.py:1:foo\n"
            result = await grep(Path("/cwd"), "foo")
            self.assertEqual(result, "a.py:1:foo\n")

    async def test_with_context(self):
        with patch("laffyhand.core.tools.file._ripgrep._rg_run", new_callable=AsyncMock) as mock:
            mock.return_value = ""
            await grep(Path("/cwd"), "foo", context=3)
            cmd = mock.call_args[0][0]
            self.assertIn("-C", cmd)
            self.assertIn("3", cmd)

    async def test_with_include(self):
        with patch("laffyhand.core.tools.file._ripgrep._rg_run", new_callable=AsyncMock) as mock:
            mock.return_value = ""
            await grep(Path("/cwd"), "foo", include="*.py")
            cmd = mock.call_args[0][0]
            self.assertIn("--glob", cmd)
            self.assertIn("*.py", cmd)

    async def test_failure_returns_none(self):
        with patch("laffyhand.core.tools.file._ripgrep._rg_run", new_callable=AsyncMock) as mock:
            mock.return_value = None
            result = await grep(Path("/cwd"), "foo")
            self.assertIsNone(result)


class TestGrepFiles(unittest.IsolatedAsyncioTestCase):
    async def test_success(self):
        with patch("laffyhand.core.tools.file._ripgrep._rg_run", new_callable=AsyncMock) as mock:
            mock.return_value = "a.py\nb.py\n"
            result = await grep_files(Path("/cwd"), "foo")
            self.assertEqual(result, ["a.py", "b.py"])

    async def test_failure_returns_none(self):
        with patch("laffyhand.core.tools.file._ripgrep._rg_run", new_callable=AsyncMock) as mock:
            mock.return_value = None
            result = await grep_files(Path("/cwd"), "foo")
            self.assertIsNone(result)


class TestGrepCount(unittest.IsolatedAsyncioTestCase):
    async def test_success(self):
        with patch("laffyhand.core.tools.file._ripgrep._rg_run", new_callable=AsyncMock) as mock:
            mock.return_value = "a.py:5\n"
            result = await grep_count(Path("/cwd"), "foo")
            self.assertEqual(result, "a.py:5\n")

    async def test_failure_returns_none(self):
        with patch("laffyhand.core.tools.file._ripgrep._rg_run", new_callable=AsyncMock) as mock:
            mock.return_value = None
            result = await grep_count(Path("/cwd"), "foo")
            self.assertIsNone(result)
