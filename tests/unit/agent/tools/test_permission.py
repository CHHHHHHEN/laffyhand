import asyncio
import unittest
from unittest.mock import patch

from laffyhand.agent.tools.permission import PermissionManager


class TestPermission(unittest.TestCase):
    def test_default_allow(self):
        pm = PermissionManager()
        self.assertTrue(pm.check("any_tool"))

    def test_deny(self):
        pm = PermissionManager()
        pm.deny("bash")
        self.assertFalse(pm.check("bash"))

    def test_allow_override(self):
        pm = PermissionManager()
        pm.deny("bash")
        pm.allow("bash")
        self.assertTrue(pm.check("bash"))

    def test_deny_one_not_others(self):
        pm = PermissionManager()
        pm.deny("bash")
        self.assertTrue(pm.check("read"))


class TestRequirePath(unittest.TestCase):
    def setUp(self):
        self.pm = PermissionManager()

    def test_within_workspace(self):
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/home/user/project/src/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_outside_no_rules_no_tty(self):
        with patch("asyncio.to_thread", side_effect=EOFError):
            with self.assertRaises(RuntimeError):
                asyncio.run(
                    self.pm.require_path("read", "/outside/file.py", "/home/user/project")
                )

    def test_outside_allowed_exact_path(self):
        self.pm.allow("read_outside_workspace:/outside/file.py")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_outside_denied_exact_path(self):
        self.pm.deny("read_outside_workspace:/outside/file.py")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/file.py", "/home/user/project")
        )
        self.assertFalse(allowed)

    def test_outside_subdir_allowed_by_parent_dir(self):
        self.pm.allow("read_outside_workspace:/outside/dir")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/dir/sub/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_outside_subdir_allowed_by_grandparent_dir(self):
        self.pm.allow("read_outside_workspace:/outside")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/a/b/c/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_outside_subdir_denied_by_parent_dir(self):
        self.pm.deny("read_outside_workspace:/outside/dir")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/dir/sub/file.py", "/home/user/project")
        )
        self.assertFalse(allowed)

    def test_outside_sibling_not_allowed(self):
        self.pm.allow("read_outside_workspace:/outside/dir_a")
        with patch("asyncio.to_thread", side_effect=EOFError):
            with self.assertRaises(RuntimeError):
                asyncio.run(
                    self.pm.require_path("read", "/outside/dir_b/file.py", "/home/user/project")
                )

    def test_outside_allowed_file_not_confused_with_dir(self):
        self.pm.allow("read_outside_workspace:/outside/file.py")
        with patch("asyncio.to_thread", side_effect=EOFError):
            with self.assertRaises(RuntimeError):
                asyncio.run(
                    self.pm.require_path("read", "/outside/other.py", "/home/user/project")
                )
