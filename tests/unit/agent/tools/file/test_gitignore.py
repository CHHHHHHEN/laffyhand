from __future__ import annotations

import os
import time
import tempfile
from pathlib import Path
from unittest import TestCase

from laffyhand.core.tools.file._gitignore import (
    GitignoreFilter,
    _GITIGNORE_CACHE,
    _GITIGNORE_CACHE_MAX,
    _load_gitignore_specs,
)


class TestGitignoreFilter(TestCase):
    def setUp(self):
        _GITIGNORE_CACHE.clear()

    def _tmp(self) -> Path:
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return Path(d.name)

    def test_no_gitignore(self):
        root = self._tmp()
        f = GitignoreFilter(root)
        self.assertFalse(f.is_ignored(root / "foo.py"))

    def test_ignores_simple_pattern(self):
        root = self._tmp()
        (root / ".gitignore").write_text("*.pyc\n")
        f = GitignoreFilter(root)
        self.assertTrue(f.is_ignored(root / "foo.pyc"))
        self.assertFalse(f.is_ignored(root / "foo.py"))

    def test_ignores_directory_by_name(self):
        root = self._tmp()
        (root / ".gitignore").write_text("__pycache__\n")
        f = GitignoreFilter(root)
        self.assertTrue(f.is_ignored(root / "__pycache__"))

    def test_filter_excludes_ignored(self):
        root = self._tmp()
        (root / ".gitignore").write_text("*.log\n")
        paths = [root / "a.py", root / "b.log", root / "c.py"]
        f = GitignoreFilter(root)
        result = f.filter(paths)
        self.assertIn(root / "a.py", result)
        self.assertNotIn(root / "b.log", result)
        self.assertIn(root / "c.py", result)

    def test_filter_with_include_ignored(self):
        root = self._tmp()
        (root / ".gitignore").write_text("*.log\n")
        paths = [root / "a.py", root / "b.log"]
        f = GitignoreFilter(root)
        result = f.filter(paths, include_ignored=True)
        self.assertEqual(result, paths)

    def test_parent_gitignore_applies_to_subdir(self):
        root = self._tmp()
        (root / ".gitignore").write_text("secret\n")
        sub = root / "sub"
        sub.mkdir()
        f = GitignoreFilter(sub)
        self.assertTrue(f.is_ignored(sub / "secret"))

    def test_negation_within_same_gitignore(self):
        root = self._tmp()
        (root / ".gitignore").write_text("*.log\n!important.log\n")
        f = GitignoreFilter(root)
        self.assertFalse(f.is_ignored(root / "important.log"))
        self.assertTrue(f.is_ignored(root / "other.log"))

    def test_cache_reuses_specs_within_ttl(self):
        root = self._tmp()
        (root / ".gitignore").write_text("*.pyc\n")
        _GITIGNORE_CACHE.clear()
        GitignoreFilter(root)
        cached_len = len(_GITIGNORE_CACHE)
        GitignoreFilter(root)
        self.assertEqual(len(_GITIGNORE_CACHE), cached_len)

    def test_cache_invalidated_on_mtime_change(self):
        root = self._tmp()
        gf = root / ".gitignore"
        gf.write_text("*.pyc\n")
        _GITIGNORE_CACHE.clear()

        f1 = GitignoreFilter(root)
        self.assertTrue(f1.is_ignored(root / "foo.pyc"))

        gf.write_text("*.py\n")
        new_mtime = time.time() + 2
        os.utime(gf, (new_mtime, new_mtime))
        f2 = GitignoreFilter(root)
        self.assertFalse(f2.is_ignored(root / "foo.pyc"))
        self.assertTrue(f2.is_ignored(root / "foo.py"))

    def test_custom_resolved_flag_skips_resolve(self):
        root = self._tmp()
        (root / ".gitignore").write_text("*.pyc\n")
        f = GitignoreFilter(root, resolved=True)
        self.assertTrue(f.is_ignored(root / "foo.pyc", resolved=True))

    def test_empty_gitignore(self):
        root = self._tmp()
        (root / ".gitignore").write_text("")
        f = GitignoreFilter(root)
        self.assertFalse(f.is_ignored(root / "anything"))

    def test_is_ignored_returns_false_for_path_outside_root(self):
        root = self._tmp()
        (root / ".gitignore").write_text("*.pyc\n")
        f = GitignoreFilter(root)
        outside = Path("/nonexistent/foo.pyc")
        self.assertFalse(f.is_ignored(outside))

    def test_cache_eviction(self):
        root = self._tmp()
        _GITIGNORE_CACHE.clear()
        for i in range(_GITIGNORE_CACHE_MAX + 5):
            d = root / f"dir{i}"
            d.mkdir()
            (d / ".gitignore").write_text("*.pyc\n")
            _load_gitignore_specs(d)
        self.assertLessEqual(len(_GITIGNORE_CACHE), _GITIGNORE_CACHE_MAX)
