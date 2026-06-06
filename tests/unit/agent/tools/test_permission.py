import asyncio
import unittest
from unittest.mock import patch

from laffyhand.core.tools.permission import PermissionManager


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
        self.pm.allow("outside_workspace:/outside/file.py")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_outside_denied_exact_path(self):
        self.pm.deny("outside_workspace:/outside/file.py")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/file.py", "/home/user/project")
        )
        self.assertFalse(allowed)

    def test_outside_subdir_allowed_by_parent_dir(self):
        self.pm.allow("outside_workspace:/outside/dir")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/dir/sub/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_outside_subdir_allowed_by_grandparent_dir(self):
        self.pm.allow("outside_workspace:/outside")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/a/b/c/file.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_outside_subdir_denied_by_parent_dir(self):
        self.pm.deny("outside_workspace:/outside/dir")
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/dir/sub/file.py", "/home/user/project")
        )
        self.assertFalse(allowed)

    def test_outside_sibling_not_allowed(self):
        self.pm.allow("outside_workspace:/outside/dir_a")
        with patch("asyncio.to_thread", side_effect=EOFError):
            with self.assertRaises(RuntimeError):
                asyncio.run(
                    self.pm.require_path("read", "/outside/dir_b/file.py", "/home/user/project")
                )

    def test_outside_allowed_file_not_confused_with_dir(self):
        self.pm.allow("outside_workspace:/outside/file.py")
        with patch("asyncio.to_thread", side_effect=EOFError):
            with self.assertRaises(RuntimeError):
                asyncio.run(
                    self.pm.require_path("read", "/outside/other.py", "/home/user/project")
                )

    def test_always_allow_file_covers_sibling(self):
        """When user always-allows a file, sibling files in same dir are also allowed."""
        with patch("asyncio.to_thread", return_value="a"):
            allowed, _ = asyncio.run(
                self.pm.require_path("read", "/outside/dir/file.py", "/home/user/project")
            )
        self.assertTrue(allowed)
        # Sibling file should be auto-allowed via propagated parent rule
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/dir/other.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_always_allow_file_covers_subdir(self):
        """When user always-allows a file, files in subdirectories under it are also allowed."""
        with patch("asyncio.to_thread", return_value="a"):
            allowed, _ = asyncio.run(
                self.pm.require_path("read", "/outside/dir/file.py", "/home/user/project")
            )
        self.assertTrue(allowed)
        # File in subdirectory should be auto-allowed
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/dir/sub/other.py", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_unified_namespace_covers_different_tool(self):
        """An 'always allow' for one tool (e.g. read) also covers other tools (e.g. list_dir)."""
        with patch("asyncio.to_thread", return_value="a"):
            allowed, _ = asyncio.run(
                self.pm.require_path("read", "/outside/dir", "/home/user/project")
            )
        self.assertTrue(allowed)
        # Different tool on a subdirectory should also be allowed
        allowed, _ = asyncio.run(
            self.pm.require_path("list_dir", "/outside/dir/sub", "/home/user/project")
        )
        self.assertTrue(allowed)

    def test_check_parent_rules_checks_path_itself(self):
        """_check_parent_rules should find a rule for the exact path, not just parents."""
        self.pm.allow("outside_workspace:/outside/dir")
        # Access the directory itself — previously required ask(),
        # now handled by _check_parent_rules
        allowed, _ = asyncio.run(
            self.pm.require_path("read", "/outside/dir", "/home/user/project")
        )
        self.assertTrue(allowed)
