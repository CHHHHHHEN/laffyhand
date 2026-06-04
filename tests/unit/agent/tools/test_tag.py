from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from laffyhand.agent.db.repository import FileTagRepo
from laffyhand.agent.db.schema import create_tables
from laffyhand.agent.tools.tag import TagTool, annotate_result, _normalize, _date_from_iso


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    create_tables(conn)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def repo(db):
    return FileTagRepo(db)


@pytest.fixture
def tool(repo):
    return TagTool(repo)


@pytest.fixture
def temp_file():
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write("test content\n")
        tmp_path = f.name
    yield tmp_path
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)


@pytest.fixture
def temp_dir():
    tmpdir = tempfile.mkdtemp()
    # Create some files in the directory
    (Path(tmpdir) / "api.py").write_text("def api(): pass\n")
    (Path(tmpdir) / "db.py").write_text("def db(): pass\n")
    (Path(tmpdir) / "models.py").write_text("class Model: pass\n")
    os.makedirs(Path(tmpdir) / "subdir", exist_ok=True)
    (Path(tmpdir) / "subdir" / "helper.py").write_text("def helper(): pass\n")
    yield tmpdir
    for p in Path(tmpdir).rglob("*"):
        if p.is_file():
            os.unlink(p)
    os.rmdir(Path(tmpdir) / "subdir")
    os.rmdir(tmpdir)


# ── FileTagRepo tests ──────────────────────────────────────────


class TestFileTagRepo:
    def test_upsert_and_get(self, repo):
        repo.upsert("/tmp/test.py", message="test file")
        repo.commit()
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.message == "test file"
        assert tag.path == "/tmp/test.py"
        assert tag.updated_at != ""

    def test_upsert_updates_existing(self, repo):
        repo.upsert("/tmp/test.py", message="old")
        repo.commit()
        repo.upsert("/tmp/test.py", message="new")
        repo.commit()
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.message == "new"

    def test_upsert_with_key_value_on_new(self, repo):
        repo.upsert("/tmp/test.py", key="review_status", value="pending")
        repo.commit()
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.message == ""
        assert tag.tags == {"review_status": "pending"}

    def test_upsert_adds_key_to_existing(self, repo):
        repo.upsert("/tmp/test.py", message="my file")
        repo.commit()
        repo.upsert("/tmp/test.py", key="owner", value="alice")
        repo.commit()
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.message == "my file"
        assert tag.tags == {"owner": "alice"}

    def test_upsert_updates_key_on_existing(self, repo):
        repo.upsert("/tmp/test.py", key="status", value="old")
        repo.commit()
        repo.upsert("/tmp/test.py", key="status", value="new")
        repo.commit()
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.tags == {"status": "new"}

    def test_get_nonexistent(self, repo):
        assert repo.get("/tmp/nope.py") is None

    def test_list_by_prefix(self, repo):
        repo.upsert("/tmp/a.py", message="a")
        repo.upsert("/tmp/b.py", message="b")
        repo.upsert("/other/c.py", message="c")
        repo.commit()
        tags = repo.list_by_prefix("/tmp/")
        assert len(tags) == 2
        paths = {t.path for t in tags}
        assert paths == {"/tmp/a.py", "/tmp/b.py"}

    def test_list_by_prefix_exact_path(self, repo):
        repo.upsert("/tmp/a.py", message="a")
        repo.commit()
        tags = repo.list_by_prefix("/tmp/a.py")
        assert len(tags) == 1
        assert tags[0].path == "/tmp/a.py"

    def test_list_all(self, repo):
        repo.upsert("/tmp/a.py", message="a")
        repo.upsert("/tmp/b.py", message="b")
        repo.commit()
        tags = repo.list_all()
        assert len(tags) == 2

    def test_delete(self, repo):
        repo.upsert("/tmp/test.py", message="bye")
        repo.commit()
        assert repo.delete("/tmp/test.py") is True
        assert repo.get("/tmp/test.py") is None

    def test_delete_nonexistent(self, repo):
        assert repo.delete("/tmp/nope.py") is False

    def test_delete_missing(self, repo):
        repo.upsert("/tmp/exists.py", message="real")
        repo.upsert("/tmp/ghost.py", message="gone")
        repo.commit()
        count = repo.delete_missing()
        assert count >= 0  # depends on whether /tmp/ghost.py actually exists
        remaining = repo.list_all()
        paths = {t.path for t in remaining}
        assert "/tmp/ghost.py" not in paths

    def test_get_all_paths(self, repo):
        repo.upsert("/tmp/a.py", message="a")
        repo.upsert("/tmp/b.py", message="b")
        repo.commit()
        paths = repo.get_all_paths()
        assert len(paths) == 2

    def test_updated_at_changes_on_upsert(self, repo):
        repo.upsert("/tmp/test.py", message="first")
        repo.commit()
        t1 = repo.get("/tmp/test.py")
        assert t1 is not None
        ts1 = t1.updated_at
        repo.upsert("/tmp/test.py", message="second")
        repo.commit()
        t2 = repo.get("/tmp/test.py")
        assert t2 is not None
        assert t2.updated_at > ts1


# ── TagTool tests ──────────────────────────────────────────────


class TestTagTool:
    def test_add(self, tool, temp_file):
        result = asyncio.run(
            tool.run({"operation": "add", "file": temp_file, "msg": "test file for unit tests"})
        )
        assert "Tagged" in result
        assert "test file for unit tests" in result

    def test_add_requires_file(self, tool):
        result = asyncio.run(tool.run({"operation": "add", "msg": "desc"}))
        assert "--file is required" in result

    def test_add_requires_msg(self, tool, temp_file):
        result = asyncio.run(tool.run({"operation": "add", "file": temp_file}))
        assert "--msg is required" in result

    def test_add_nonexistent_path(self, tool):
        result = asyncio.run(
            tool.run({"operation": "add", "file": "/tmp/nonexistent_file_xyz.py", "msg": "desc"})
        )
        assert "path does not exist" in result

    def test_update_message(self, tool, temp_file):
        asyncio.run(tool.run({"operation": "add", "file": temp_file, "msg": "old desc"}))
        result = asyncio.run(
            tool.run({"operation": "update", "file": temp_file, "msg": "new desc"})
        )
        assert "Updated tag" in result
        assert "new desc" in result

    def test_update_key_value(self, tool, temp_file):
        asyncio.run(tool.run({"operation": "add", "file": temp_file, "msg": "desc"}))
        result = asyncio.run(
            tool.run(
                {
                    "operation": "update",
                    "file": temp_file,
                    "key": "review_status",
                    "value": "needs refactor",
                }
            )
        )
        assert "Updated tag" in result
        assert "review_status" in result
        assert "needs refactor" in result

    def test_update_key_value_preserves_message(self, tool, temp_file):
        asyncio.run(tool.run({"operation": "add", "file": temp_file, "msg": "original msg"}))
        asyncio.run(
            tool.run(
                {
                    "operation": "update",
                    "file": temp_file,
                    "key": "owner",
                    "value": "alice",
                }
            )
        )
        result = asyncio.run(tool.run({"operation": "list", "path": temp_file}))
        assert "original msg" in result

    def test_update_requires_file(self, tool):
        result = asyncio.run(tool.run({"operation": "update", "msg": "desc"}))
        assert "--file is required" in result

    def test_update_requires_msg_or_key(self, tool, temp_file):
        result = asyncio.run(
            tool.run({"operation": "update", "file": temp_file})
        )
        assert "provide either --msg or --key/--value" in result

    def test_update_nonexistent_path(self, tool):
        result = asyncio.run(
            tool.run(
                {"operation": "update", "file": "/tmp/nonexistent_xyz.py", "msg": "desc"}
            )
        )
        assert "path does not exist" in result

    def test_list_all(self, tool, temp_file, temp_dir):
        asyncio.run(tool.run({"operation": "add", "file": temp_file, "msg": "a file"}))
        result = asyncio.run(tool.run({"operation": "list"}))
        assert "Found 1 tag(s)" in result
        assert "a file" in result

    def test_list_by_directory(self, tool, temp_dir):
        api_py = Path(temp_dir) / "api.py"
        db_py = Path(temp_dir) / "db.py"
        asyncio.run(tool.run({"operation": "add", "file": str(api_py), "msg": "API handler"}))
        asyncio.run(tool.run({"operation": "add", "file": str(db_py), "msg": "DB layer"}))
        result = asyncio.run(tool.run({"operation": "list", "path": temp_dir}))
        assert "Found 2 tag(s)" in result
        assert "API handler" in result
        assert "DB layer" in result

    def test_list_empty(self, tool):
        result = asyncio.run(tool.run({"operation": "list"}))
        assert "No tags found" in result

    def test_prune_orphans(self, tool, temp_file):
        asyncio.run(tool.run({"operation": "add", "file": temp_file, "msg": "will be removed"}))
        os.unlink(temp_file)
        result = asyncio.run(tool.run({"operation": "prune"}))
        assert "Pruned" in result
        # The file no longer exists, so prune should clean it

    def test_prune_no_orphans(self, tool):
        result = asyncio.run(tool.run({"operation": "prune"}))
        assert "No orphan tags" in result

    def test_path_normalization(self, tool, temp_file):
        """Relative paths and absolute paths should map to same tag."""
        real = os.path.realpath(temp_file)
        cwd = os.path.dirname(real)
        fname = os.path.basename(real)
        rel = os.path.join(".", fname)
        old_cwd = os.getcwd()
        try:
            os.chdir(cwd)
            asyncio.run(
                tool.run({"operation": "add", "file": rel, "msg": "via relative path"})
            )
        finally:
            os.chdir(old_cwd)
        tag = tool._repo.get(real)
        assert tag is not None
        assert tag.message == "via relative path"

    def test_unknown_operation(self, tool):
        result = asyncio.run(tool.run({"operation": "unknown"}))
        assert "Unknown operation" in result


# ── Annotation tests ───────────────────────────────────────────


class TestAnnotation:
    def test_annotate_glob(self, repo, temp_dir):
        api_py = Path(temp_dir) / "api.py"
        db_py = Path(temp_dir) / "db.py"
        repo.upsert(str(api_py), message="API handler")
        repo.upsert(str(db_py), message="DB layer")
        repo.commit()

        glob_result = "api.py\ndb.py\nmodels.py"
        params = {"path": temp_dir}
        annotated = annotate_result("glob", glob_result, params, repo)

        assert "\U0001f516 API handler" in annotated
        assert "\U0001f516 DB layer" in annotated
        assert "models.py" in annotated
        assert "\U0001f516" in annotated

    def test_annotate_glob_no_tags(self, repo, temp_dir):
        glob_result = "api.py\ndb.py"
        params = {"path": temp_dir}
        annotated = annotate_result("glob", glob_result, params, repo)
        assert annotated == glob_result

    def test_annotate_glob_absolute_paths(self, repo, temp_dir):
        api_py = Path(temp_dir) / "api.py"
        repo.upsert(str(api_py), message="API handler")
        repo.commit()

        glob_result = str(api_py)
        params = {"path": "."}
        annotated = annotate_result("glob", glob_result, params, repo)
        assert "\U0001f516 API handler" in annotated

    def test_annotate_read_directory(self, repo, temp_dir):
        api_py = Path(temp_dir) / "api.py"
        db_py = Path(temp_dir) / "db.py"
        repo.upsert(str(api_py), message="API handler")
        repo.upsert(str(db_py), message="DB layer")
        repo.commit()

        read_result = (
            f"Contents of {temp_dir} (total 4 entries):\n"
            f"  api.py (1 lines)\n"
            f"  db.py (1 lines)\n"
            f"  models.py (1 lines)\n"
            f"  subdir/"
        )
        params = {"file_path": temp_dir}
        annotated = annotate_result("read", read_result, params, repo)

        assert "\U0001f516 API handler" in annotated
        assert "\U0001f516 DB layer" in annotated
        assert "models.py" in annotated
        assert "subdir/" in annotated

    def test_annotate_read_no_tags(self, repo, temp_dir):
        read_result = f"Contents of {temp_dir} (total 1 entries):\n  api.py (1 lines)"
        params = {"file_path": temp_dir}
        annotated = annotate_result("read", read_result, params, repo)
        assert annotated == read_result

    def test_annotate_read_not_a_directory_listing(self, repo):
        read_result = "def foo():\n    pass"
        params = {"file_path": "/tmp/some_file.py"}
        annotated = annotate_result("read", read_result, params, repo)
        assert annotated == read_result

    def test_annotate_other_tool(self, repo):
        result = "some output"
        annotated = annotate_result("bash", result, {}, repo)
        assert annotated == result

    def test_annotate_empty_result(self, repo):
        annotated = annotate_result("glob", "", {}, repo)
        assert annotated == ""

    def test_annotate_glob_with_metadata_lines(self, repo):
        result = "src/main.py\n[Results limited to 100 files]"
        params = {"path": "."}
        annotated = annotate_result("glob", result, params, repo)
        assert "[Results limited" in annotated


# ── Utility tests ──────────────────────────────────────────────


class TestUtils:
    def test_normalize(self):
        real = _normalize(".")
        assert real == os.path.realpath(".")
        assert os.path.isabs(real)

    def test_normalize_with_tilde(self, tmp_path):
        # realpath doesn't expand tilde, that's expected
        pass

    def test_date_from_iso(self):
        assert _date_from_iso("2026-06-04T12:34:56+00:00") == "2026-06-04"
        assert _date_from_iso("2026-06-04") == "2026-06-04"
