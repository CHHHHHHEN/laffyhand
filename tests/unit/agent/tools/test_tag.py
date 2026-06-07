from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from laffyhand.core.db.repository import FileTagRepo
from laffyhand.core.db.schema import create_tables
from laffyhand.core.db.models import FileTag
from laffyhand.core.tools.tag import TagTool, annotate_result, format_tag_summary, _normalize, _date_from_iso, _coerce_dict, _coerce_list
from laffyhand.core.db.repository.tag import _parse_json_dict, _parse_json_list


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
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


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
        assert tag.status == "active"

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

    def test_upsert_with_status(self, repo):
        repo.upsert("/tmp/test.py", message="test", status="stale")
        repo.commit()
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.status == "stale"

    def test_upsert_preserves_status_when_not_given(self, repo):
        repo.upsert("/tmp/test.py", message="first", status="stale")
        repo.commit()
        repo.upsert("/tmp/test.py", message="second")
        repo.commit()
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.message == "second"
        assert tag.status == "stale"

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

    def test_list_by_status(self, repo):
        repo.upsert("/tmp/a.py", message="active file")
        repo.upsert("/tmp/b.py", message="stale file", status="stale")
        repo.commit()
        active = repo.list_by_status("active")
        stale = repo.list_by_status("stale")
        assert len(active) == 1
        assert active[0].path == "/tmp/a.py"
        assert len(stale) == 1
        assert stale[0].path == "/tmp/b.py"

    def test_mark_stale(self, repo):
        repo.upsert("/tmp/test.py", message="test")
        repo.commit()
        assert repo.mark_stale("/tmp/test.py") is True
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.status == "stale"

    def test_mark_stale_nonexistent(self, repo):
        assert repo.mark_stale("/tmp/nope.py") is False

    def test_mark_stale_already_stale(self, repo):
        repo.upsert("/tmp/test.py", message="test", status="stale")
        repo.commit()
        # mark_stale only affects active tags
        assert repo.mark_stale("/tmp/test.py") is False

    def test_mark_stale_missing(self, repo, temp_file):
        repo.upsert(temp_file, message="exists")
        repo.upsert("/tmp/ghost_tag.py", message="ghost")
        repo.commit()
        marked = repo.mark_stale_missing()
        assert marked > 0
        ghost = repo.get("/tmp/ghost_tag.py")
        assert ghost is not None
        assert ghost.status == "stale"
        existing = repo.get(temp_file)
        assert existing is not None
        assert existing.status == "active"

    def test_delete(self, repo):
        repo.upsert("/tmp/test.py", message="bye")
        repo.commit()
        assert repo.delete("/tmp/test.py") is True
        assert repo.get("/tmp/test.py") is None

    def test_delete_nonexistent(self, repo):
        assert repo.delete("/tmp/nope.py") is False

    def test_delete_missing(self, repo, tmp_path):
        target = tmp_path / "exists.py"
        target.write_text("real")
        repo.upsert(str(target), message="real")
        ghost = str(tmp_path / "ghost.py")
        repo.upsert(ghost, message="gone")
        repo.commit()
        count = repo.delete_missing()
        assert count == 1
        remaining = repo.list_all()
        paths = {t.path for t in remaining}
        assert ghost not in paths

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

    def test_upsert_with_exports(self, repo):
        repo.upsert("/tmp/test.py", message="test file", exports={"MyClass": "class", "my_func": "function"})
        repo.commit()
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.exports == {"MyClass": "class", "my_func": "function"}

    def test_upsert_with_side_effects(self, repo):
        repo.upsert("/tmp/test.py", message="test file", side_effects="registers signal handlers on import")
        repo.commit()
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.side_effects == "registers signal handlers on import"

    def test_upsert_with_depends_on(self, repo):
        repo.upsert("/tmp/test.py", message="test file", depends_on=["redis", "database.session"])
        repo.commit()
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.depends_on == ["redis", "database.session"]

    def test_upsert_all_structured_fields(self, repo):
        repo.upsert(
            "/tmp/test.py",
            message="test file",
            exports={"Util": "class"},
            side_effects="monkey-patches os.path",
            depends_on=["requests", "sqlalchemy"],
        )
        repo.commit()
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.exports == {"Util": "class"}
        assert tag.side_effects == "monkey-patches os.path"
        assert tag.depends_on == ["requests", "sqlalchemy"]

    def test_upsert_preserves_exports_on_message_update(self, repo):
        repo.upsert("/tmp/test.py", message="first", exports={"A": "class"})
        repo.commit()
        repo.upsert("/tmp/test.py", message="second")
        repo.commit()
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.message == "second"
        assert tag.exports == {"A": "class"}

    def test_upsert_preserves_side_effects_on_message_update(self, repo):
        repo.upsert("/tmp/test.py", message="first", side_effects="sets global state")
        repo.commit()
        repo.upsert("/tmp/test.py", message="second")
        repo.commit()
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.message == "second"
        assert tag.side_effects == "sets global state"

    def test_upsert_preserves_depends_on_on_message_update(self, repo):
        repo.upsert("/tmp/test.py", message="first", depends_on=["libfoo"])
        repo.commit()
        repo.upsert("/tmp/test.py", message="second")
        repo.commit()
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.message == "second"
        assert tag.depends_on == ["libfoo"]

    def test_status_in_all_listings(self, repo):
        repo.upsert("/tmp/a.py", message="active", status="active")
        repo.upsert("/tmp/b.py", message="stale", status="stale")
        repo.commit()
        for tag in repo.list_all():
            assert tag.status in ("active", "stale")
        for tag in repo.list_by_prefix("/tmp/"):
            assert tag.status in ("active", "stale")


# ── TagTool tests ──────────────────────────────────────────────


class TestTagTool:
    def test_add(self, tool, temp_file):
        result = asyncio.run(
            tool.run({"operation": "add", "file_path": temp_file, "message": "test file for unit tests"})
        )
        assert "Tagged" in result
        assert "test file for unit tests" in result

    def test_add_requires_file(self, tool):
        result = asyncio.run(tool.run({"operation": "add", "message": "desc"}))
        assert "--file_path is required" in result

    def test_add_requires_msg(self, tool, temp_file):
        result = asyncio.run(tool.run({"operation": "add", "file_path": temp_file}))
        assert "--message is required" in result

    def test_add_nonexistent_path(self, tool):
        result = asyncio.run(
            tool.run({"operation": "add", "file_path": "/tmp/nonexistent_file_xyz.py", "message": "desc"})
        )
        assert "path does not exist" in result

    def test_add_resets_stale(self, tool, temp_file):
        """Adding a tag to a file that was previously marked stale resets to active."""
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "message": "first"}))
        # Manually mark stale
        tool._repo.mark_stale(temp_file)
        tool._repo.commit()
        # Re-add — should show diff since a tag already exists (stale)
        result = asyncio.run(
            tool.run({"operation": "add", "file_path": temp_file, "message": "re-tagged"})
        )
        assert "updated existing tag" in result
        assert "first → re-tagged" in result
        assert "re-tagged" in result
        tag = tool._repo.get(temp_file)
        assert tag is not None
        assert tag.status == "active"
        assert tag.message == "re-tagged"

    def test_update_message(self, tool, temp_file):
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "message": "old desc"}))
        result = asyncio.run(
            tool.run({"operation": "update", "file_path": temp_file, "message": "new desc"})
        )
        assert "Updated tag" in result
        assert "message:" in result
        assert "old desc → new desc" in result
        assert "new desc" in result

    def test_update_key_value(self, tool, temp_file):
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "message": "desc"}))
        result = asyncio.run(
            tool.run(
                {
                    "operation": "update",
                    "file_path": temp_file,
                    "key": "review_status",
                    "value": "needs refactor",
                }
            )
        )
        assert "Updated tag" in result
        assert "review_status:" in result
        assert "(none) → needs refactor" in result
        assert "needs refactor" in result

    def test_update_key_value_preserves_message(self, tool, temp_file):
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "message": "original msg"}))
        asyncio.run(
            tool.run(
                {
                    "operation": "update",
                    "file_path": temp_file,
                    "key": "owner",
                    "value": "alice",
                }
            )
        )
        result = asyncio.run(tool.run({"operation": "list", "path": temp_file}))
        assert "original msg" in result

    def test_update_requires_file(self, tool):
        result = asyncio.run(tool.run({"operation": "update", "message": "desc"}))
        assert "--file_path is required" in result

    def test_update_requires_msg_or_key(self, tool, temp_file):
        result = asyncio.run(
            tool.run({"operation": "update", "file_path": temp_file})
        )
        assert "provide --message, --exports/--side_effects/--depends_on, or --key/--value" in result

    def test_update_nonexistent_path(self, tool):
        result = asyncio.run(
            tool.run(
                {"operation": "update", "file_path": "/tmp/nonexistent_xyz.py", "message": "desc"}
            )
        )
        assert "path does not exist" in result

    def test_list_all(self, tool, temp_file, temp_dir):
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "message": "a file"}))
        result = asyncio.run(tool.run({"operation": "list"}))
        assert "Found 1 tag(s)" in result
        assert "a file" in result

    def test_list_by_directory(self, tool, temp_dir):
        api_py = Path(temp_dir) / "api.py"
        db_py = Path(temp_dir) / "db.py"
        asyncio.run(tool.run({"operation": "add", "file_path": str(api_py), "message": "API handler"}))
        asyncio.run(tool.run({"operation": "add", "file_path": str(db_py), "message": "DB layer"}))
        result = asyncio.run(tool.run({"operation": "list", "path": temp_dir}))
        assert "Found 2 tag(s)" in result
        assert "API handler" in result
        assert "DB layer" in result

    def test_list_by_status(self, tool, temp_file):
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "message": "test file"}))
        # Mark stale manually
        tool._repo.mark_stale(temp_file)
        tool._repo.commit()
        result = asyncio.run(tool.run({"operation": "list", "status": "stale"}))
        assert "Found 1 tag(s)" in result
        assert "STALE" in result

    def test_list_empty(self, tool):
        result = asyncio.run(tool.run({"operation": "list"}))
        assert "No tags found" in result

    def test_batch_add(self, tool, temp_dir):
        api_py = Path(temp_dir) / "api.py"
        db_py = Path(temp_dir) / "db.py"
        result = asyncio.run(
            tool.run(
                {
                    "operation": "batch",
                    "tags": [
                        {"file_path": str(api_py), "message": "API handler"},
                        {"file_path": str(db_py), "message": "DB layer"},
                    ],
                }
            )
        )
        assert "Batch processed 2 tag(s)" in result
        assert "API handler" in result
        assert "DB layer" in result
        # Verify persisted
        assert tool._repo.get(str(api_py)) is not None
        assert tool._repo.get(str(db_py)) is not None

    def test_batch_skip_nonexistent(self, tool):
        result = asyncio.run(
            tool.run(
                {
                    "operation": "batch",
                    "tags": [
                        {"file_path": "/tmp/nonexistent_xyz.py", "message": "ghost"},
                    ],
                }
            )
        )
        assert "Skipped" in result
        assert "path not found" in result

    def test_batch_empty(self, tool):
        result = asyncio.run(tool.run({"operation": "batch"}))
        assert "--tags list is required" in result

    def test_prune_marks_stale(self, tool, temp_file):
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "message": "will be stale"}))
        assert os.path.exists(temp_file)
        os.unlink(temp_file)
        result = asyncio.run(tool.run({"operation": "prune"}))
        assert "Marked" in result
        assert "stale" in result
        # Tag should still exist but marked stale
        tag = tool._repo.get(os.path.realpath(temp_file))
        assert tag is not None
        assert tag.status == "stale"

    def test_prune_delete_mode(self, tool, temp_file):
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "message": "will be deleted"}))
        os.unlink(temp_file)
        result = asyncio.run(tool.run({"operation": "prune", "delete": True}))
        assert "deleted" in result
        # Tag should be gone
        assert tool._repo.get(os.path.realpath(temp_file)) is None

    def test_prune_no_orphans(self, tool):
        result = asyncio.run(tool.run({"operation": "prune"}))
        assert "No tags to mark as stale" in result

    def test_path_normalization(self, tool, temp_file):
        """Relative paths and absolute paths should map to same tag."""
        real = os.path.realpath(temp_file)
        tmpdir = os.path.dirname(real)
        fname = os.path.basename(real)
        rel = os.path.join(".", fname)
        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            asyncio.run(
                tool.run({"operation": "add", "file_path": rel, "message": "via relative path"})
            )
        finally:
            os.chdir(old_cwd)
        tag = tool._repo.get(real)
        assert tag is not None
        assert tag.message == "via relative path"

    def test_unknown_operation(self, tool):
        result = asyncio.run(tool.run({"operation": "unknown"}))
        assert "Unknown operation" in result

    def test_stale_note_in_output(self, tool, temp_file):
        """Verify that the agent maintenance note appears in output."""
        result = asyncio.run(
            tool.run({"operation": "add", "file_path": temp_file, "message": "test"})
        )
        assert "Each file or directory can have only one tag" in result
        assert "Tags are maintained by AI agents" in result


    def test_add_with_exports(self, tool, temp_file):
        result = asyncio.run(
            tool.run({
                "operation": "add",
                "file_path": temp_file,
                "message": "test file",
                "exports": {"MyClass": "class", "my_func": "function"},
            })
        )
        assert "Tagged" in result
        tag = tool._repo.get(os.path.realpath(temp_file))
        assert tag is not None
        assert tag.exports == {"MyClass": "class", "my_func": "function"}

    def test_add_with_side_effects(self, tool, temp_file):
        result = asyncio.run(
            tool.run({
                "operation": "add",
                "file_path": temp_file,
                "message": "test file",
                "side_effects": "registers signal handlers on import",
            })
        )
        assert "Tagged" in result
        tag = tool._repo.get(os.path.realpath(temp_file))
        assert tag is not None
        assert tag.side_effects == "registers signal handlers on import"

    def test_add_with_depends_on(self, tool, temp_file):
        result = asyncio.run(
            tool.run({
                "operation": "add",
                "file_path": temp_file,
                "message": "test file",
                "depends_on": ["redis", "database.session"],
            })
        )
        assert "Tagged" in result
        tag = tool._repo.get(os.path.realpath(temp_file))
        assert tag is not None
        assert tag.depends_on == ["redis", "database.session"]

    def test_update_exports(self, tool, temp_file):
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "message": "base"}))
        result = asyncio.run(
            tool.run({
                "operation": "update",
                "file_path": temp_file,
                "exports": {"NewClass": "class"},
            })
        )
        assert "Updated tag" in result
        assert "exports: updated" in result
        tag = tool._repo.get(os.path.realpath(temp_file))
        assert tag is not None
        assert tag.exports == {"NewClass": "class"}

    def test_update_side_effects(self, tool, temp_file):
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "message": "base"}))
        result = asyncio.run(
            tool.run({
                "operation": "update",
                "file_path": temp_file,
                "side_effects": "modifies global config",
            })
        )
        assert "Updated tag" in result
        assert "side_effects: updated" in result
        tag = tool._repo.get(os.path.realpath(temp_file))
        assert tag is not None
        assert tag.side_effects == "modifies global config"

    def test_update_depends_on(self, tool, temp_file):
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "message": "base"}))
        result = asyncio.run(
            tool.run({
                "operation": "update",
                "file_path": temp_file,
                "depends_on": ["libfoo", "libbar"],
            })
        )
        assert "Updated tag" in result
        assert "depends_on: updated" in result
        tag = tool._repo.get(os.path.realpath(temp_file))
        assert tag is not None
        assert tag.depends_on == ["libfoo", "libbar"]

    def test_list_shows_exports_section(self, tool, temp_file):
        asyncio.run(
            tool.run({
                "operation": "add",
                "file_path": temp_file,
                "message": "test file",
                "exports": {"MyClass": "class", "CONST": "constant"},
                "side_effects": "patches stdlib",
                "depends_on": ["os", "sys"],
            })
        )
        result = asyncio.run(tool.run({"operation": "list", "path": temp_file}))
        assert "exports:" in result
        assert "MyClass: class" in result
        assert "CONST: constant" in result
        assert "side_effects: patches stdlib" in result
        assert "depends_on:" in result
        assert "os" in result
        assert "sys" in result

    def test_batch_with_exports(self, tool, temp_dir):
        api_py = Path(temp_dir) / "api.py"
        result = asyncio.run(
            tool.run({
                "operation": "batch",
                "tags": [{
                    "file_path": str(api_py),
                    "message": "API handler",
                    "exports": {"handle_request": "function"},
                    "side_effects": "sets up routes",
                }],
            })
        )
        assert "Batch processed 1 tag(s)" in result
        tag = tool._repo.get(str(api_py))
        assert tag is not None
        assert tag.exports == {"handle_request": "function"}
        assert tag.side_effects == "sets up routes"


# ── Directory tag tests ─────────────────────────────────────────


class TestDirectoryTag:
    """Tests for tagging directories."""

    def test_add_directory_tag(self, tool, temp_dir):
        result = asyncio.run(
            tool.run({"operation": "add", "file_path": temp_dir, "message": "package directory"})
        )
        assert "Tagged" in result
        assert "package directory" in result
        tag = tool._repo.get(os.path.realpath(temp_dir))
        assert tag is not None
        assert tag.message == "package directory"
        assert tag.status == "active"

    def test_update_directory_tag(self, tool, temp_dir):
        asyncio.run(tool.run({"operation": "add", "file_path": temp_dir, "message": "old desc"}))
        result = asyncio.run(
            tool.run({"operation": "update", "file_path": temp_dir, "message": "new desc"})
        )
        assert "Updated tag" in result
        assert "old desc \u2192 new desc" in result
        tag = tool._repo.get(os.path.realpath(temp_dir))
        assert tag is not None
        assert tag.message == "new desc"

    def test_list_shows_directory_self_tag(self, tool, temp_dir):
        """list --path <dir> should include the directory's own tag."""
        asyncio.run(tool.run({"operation": "add", "file_path": temp_dir, "message": "my package"}))
        result = asyncio.run(tool.run({"operation": "list", "path": temp_dir}))
        assert "my package" in result

    def test_list_shows_directory_and_children(self, tool, temp_dir):
        """list --path <dir> should show the dir's own tag before children tags."""
        api_py = Path(temp_dir) / "api.py"
        asyncio.run(tool.run({"operation": "add", "file_path": temp_dir, "message": "my package"}))
        asyncio.run(tool.run({"operation": "add", "file_path": str(api_py), "message": "API handler"}))
        result = asyncio.run(tool.run({"operation": "list", "path": temp_dir}))
        assert "my package" in result
        assert "API handler" in result

    def test_list_directory_no_self_tag_shows_children_only(self, tool, temp_dir):
        """Directory with no tag of its own should only show children."""
        api_py = Path(temp_dir) / "api.py"
        asyncio.run(tool.run({"operation": "add", "file_path": str(api_py), "message": "API handler"}))
        result = asyncio.run(tool.run({"operation": "list", "path": temp_dir}))
        # Dir itself has no tag, so only the child tag appears
        assert "API handler" in result
        assert "Found 1 tag(s)" in result

    def test_batch_directory(self, tool, temp_dir):
        result = asyncio.run(
            tool.run({
                "operation": "batch",
                "tags": [
                    {"file_path": temp_dir, "message": "package dir"},
                ],
            })
        )
        assert "Batch processed 1 tag(s)" in result
        assert "package dir" in result
        tag = tool._repo.get(os.path.realpath(temp_dir))
        assert tag is not None
        assert tag.message == "package dir"

    def test_prune_directory_tag(self, tool, temp_dir):
        """prune should handle directory tags correctly (os.path.exists works for dirs)."""
        asyncio.run(tool.run({"operation": "add", "file_path": temp_dir, "message": "will be removed"}))
        # Remove the directory
        import shutil
        shutil.rmtree(temp_dir)
        result = asyncio.run(tool.run({"operation": "prune"}))
        assert "Marked" in result
        assert "stale" in result
        tag = tool._repo.get(os.path.realpath(temp_dir))
        assert tag is not None
        assert tag.status == "stale"


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
        annotated = annotate_result("list_dir", read_result, params, repo)

        assert "\U0001f516 API handler" in annotated
        assert "\U0001f516 DB layer" in annotated
        assert "models.py" in annotated
        assert "subdir/" in annotated

    def test_annotate_read_nested_directory(self, repo, temp_dir):
        """Nested files should resolve against their parent directory, not the root."""
        nested_py = Path(temp_dir) / "subdir" / "helper.py"
        api_py = Path(temp_dir) / "api.py"
        repo.upsert(str(nested_py), message="Helper module")
        repo.upsert(str(api_py), message="API handler")
        repo.commit()

        read_result = (
            f"Contents of {temp_dir} (depth=2):\n"
            f"  api.py (1 lines)\n"
            f"  subdir/\n"
            f"    helper.py (1 lines)\n"
        )
        params = {"file_path": temp_dir}
        annotated = annotate_result("list_dir", read_result, params, repo)

        assert "\U0001f516 API handler" in annotated
        assert "\U0001f516 Helper module" in annotated

    def test_annotate_read_deeply_nested(self, repo, temp_dir):
        """Files at depth >= 3 should resolve against their actual directory."""
        deep_py = Path(temp_dir) / "subdir" / "deep" / "deep.py"
        repo.upsert(str(deep_py), message="Deeply nested module")
        repo.commit()

        read_result = (
            f"Contents of {temp_dir} (depth=3):\n"
            f"  subdir/\n"
            f"    deep/\n"
            f"      deep.py (1 lines)\n"
        )
        params = {"file_path": temp_dir}
        annotated = annotate_result("list_dir", read_result, params, repo)

        assert "\U0001f516 Deeply nested module" in annotated

    def test_annotate_read_same_filename_in_subdir(self, repo, temp_dir):
        """A file named __init__.py in a subdir must NOT resolve to root __init__.py."""
        nested_init = Path(temp_dir) / "subdir" / "__init__.py"
        root_init = Path(temp_dir) / "__init__.py"
        repo.upsert(str(nested_init), message="Subpackage init")
        repo.upsert(str(root_init), message="Root package init")
        repo.commit()

        read_result = (
            f"Contents of {temp_dir} (depth=2):\n"
            f"  __init__.py (1 lines)\n"
            f"  subdir/\n"
            f"    __init__.py (1 lines)\n"
        )
        params = {"file_path": temp_dir}
        annotated = annotate_result("list_dir", read_result, params, repo)

        assert "\U0001f516 Root package init" in annotated
        assert "\U0001f516 Subpackage init" in annotated

    def test_annotate_read_multiple_subdirs(self, repo, temp_dir):
        """Sibling subdirectories with same-named files should each resolve correctly."""
        lib_init = Path(temp_dir) / "lib" / "__init__.py"
        cli_init = Path(temp_dir) / "cli" / "__init__.py"
        repo.upsert(str(lib_init), message="Lib package init")
        repo.upsert(str(cli_init), message="CLI package init")
        repo.commit()

        read_result = (
            f"Contents of {temp_dir} (depth=2):\n"
            f"  cli/\n"
            f"    __init__.py (1 lines)\n"
            f"  lib/\n"
            f"    __init__.py (1 lines)\n"
        )
        params = {"file_path": temp_dir}
        annotated = annotate_result("list_dir", read_result, params, repo)

        assert "\U0001f516 CLI package init" in annotated
        assert "\U0001f516 Lib package init" in annotated

    def test_annotate_read_no_tags(self, repo, temp_dir):
        read_result = f"Contents of {temp_dir} (total 1 entries):\n  api.py (1 lines)"
        params = {"file_path": temp_dir}
        annotated = annotate_result("list_dir", read_result, params, repo)
        assert annotated == read_result

    def test_annotate_read_not_a_directory_listing(self, repo):
        read_result = "def foo():\n    pass"
        params = {"file_path": "/tmp/some_file.py"}
        annotated = annotate_result("list_dir", read_result, params, repo)
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

    def test_annotate_glob_stale_tag(self, repo, temp_dir):
        """Stale tags should show the STALE marker in annotation."""
        api_py = Path(temp_dir) / "api.py"
        repo.upsert(str(api_py), message="API handler", status="stale")
        repo.commit()

        glob_result = "api.py"
        params = {"path": temp_dir}
        annotated = annotate_result("glob", glob_result, params, repo)
        assert "STALE" in annotated
        assert "\U0001f516" in annotated

    def test_annotate_glob_show_tags_false(self, repo, temp_dir):
        api_py = Path(temp_dir) / "api.py"
        repo.upsert(str(api_py), message="API handler")
        repo.commit()

        glob_result = "api.py"
        params = {"path": temp_dir, "show_tags": False}
        annotated = annotate_result("glob", glob_result, params, repo)
        assert annotated == "api.py"
        assert "\U0001f516" not in annotated

    def test_annotate_read_show_tags_false(self, repo, temp_dir):
        api_py = Path(temp_dir) / "api.py"
        repo.upsert(str(api_py), message="API handler")
        repo.commit()

        read_result = f"Contents of {temp_dir} (total 1 entries):\n  api.py (1 lines)"
        params = {"file_path": temp_dir, "show_tags": False}
        annotated = annotate_result("read", read_result, params, repo)
        assert "\U0001f516" not in annotated

    # ── Directory annotation in list_dir ────────────────────────

    def test_annotate_read_directory_self_tag(self, repo, temp_dir):
        """A tagged directory should have its tag retrievable."""
        repo.upsert(str(temp_dir), message="source package")
        repo.commit()
        assert repo.get(str(temp_dir)) is not None

    def test_annotate_read_directory_entry_tagged(self, repo, temp_dir):
        """A subdirectory entry with a tag should show annotation."""
        sub = Path(temp_dir) / "sub"
        sub.mkdir()
        repo.upsert(str(sub), message="sub package")
        repo.commit()

        read_result = (
            f"Contents of {temp_dir} (depth=2):\n"
            f"  api.py (1 lines)\n"
            f"  sub/\n"
        )
        params = {"file_path": temp_dir}
        annotated = annotate_result("list_dir", read_result, params, repo)
        assert "\U0001f516 sub package" in annotated
        assert "sub/" in annotated

    def test_annotate_read_directory_entry_no_tag(self, repo, temp_dir):
        """A subdirectory without a tag should not be annotated."""
        sub = Path(temp_dir) / "sub"
        sub.mkdir()

        read_result = (
            f"Contents of {temp_dir} (depth=2):\n"
            f"  api.py (1 lines)\n"
            f"  sub/\n"
        )
        params = {"file_path": temp_dir}
        annotated = annotate_result("list_dir", read_result, params, repo)
        assert "sub/" in annotated
        assert "\U0001f516" not in annotated

    def test_annotate_read_tracked_children_after_tagged_directory(self, repo, temp_dir):
        """Files inside a tagged subdirectory should still be resolved correctly."""
        sub = Path(temp_dir) / "sub"
        sub.mkdir()
        inner = sub / "inner.py"
        repo.upsert(str(sub), message="sub package")
        repo.upsert(str(inner), message="inner module")
        repo.commit()

        read_result = (
            f"Contents of {temp_dir} (depth=3):\n"
            f"  sub/\n"
            f"    inner.py (1 lines)\n"
        )
        params = {"file_path": temp_dir}
        annotated = annotate_result("list_dir", read_result, params, repo)
        assert "\U0001f516 sub package" in annotated
        assert "\U0001f516 inner module" in annotated

    def test_annotate_read_directory_show_tags_false(self, repo, temp_dir):
        """show_tags=false should suppress directory tag annotation."""
        sub = Path(temp_dir) / "sub"
        sub.mkdir()
        repo.upsert(str(sub), message="sub package")
        repo.commit()

        read_result = (
            f"Contents of {temp_dir} (depth=2):\n"
            f"  sub/\n"
        )
        params = {"file_path": temp_dir, "show_tags": False}
        annotated = annotate_result("list_dir", read_result, params, repo)
        assert "\U0001f516" not in annotated

# ── Utility tests ──────────────────────────────────────────────


class TestUtils:
    def test_normalize(self):
        real = _normalize(".")
        assert real == os.path.realpath(".")
        assert os.path.isabs(real)

    def test_normalize_with_tilde(self, tmp_path):
        # realpath doesn't expand tilde, that's expected
        result = _normalize("~")
        assert "~" in result
        assert os.path.isabs(result)

    def test_date_from_iso(self):
        assert _date_from_iso("2026-06-04T12:34:56+00:00") == "2026-06-04"
        assert _date_from_iso("2026-06-04") == "2026-06-04"

    def test_format_tag_summary_with_exports(self):
        tag = FileTag(
            path="/tmp/test.py",
            message="test file",
            tags={},
            updated_at="2026-06-04T12:00:00+00:00",
            exports={"MyClass": "class", "my_func": "function"},
            side_effects="monkey-patches os.path",
            depends_on=["os", "sys"],
        )
        summary = format_tag_summary(tag)
        assert "\U0001f516 test file" in summary
        assert "MyClass, my_func" in summary
        assert "side effects: yes" in summary
        assert "(2026-06-04)" in summary

    def test_format_tag_summary_no_truncation(self):
        long_msg = "a" * 200
        tag = FileTag(
            path="/tmp/test.py",
            message=long_msg,
            tags={},
            updated_at="2026-06-04T12:00:00+00:00",
        )
        summary = format_tag_summary(tag)
        assert long_msg in summary
        assert "..." not in summary


class TestCoercion:
    """Tests for _coerce_dict, _coerce_list, _parse_json_dict, _parse_json_list."""

    # ── _coerce_dict ──────────────────────────────────────────────

    def test_coerce_dict_already_dict(self):
        assert _coerce_dict({"a": "b"}) == {"a": "b"}

    def test_coerce_dict_none(self):
        assert _coerce_dict(None) is None

    def test_coerce_dict_json_string(self):
        result = _coerce_dict('{"ChatInput": "function"}')
        assert result == {"ChatInput": "function"}

    def test_coerce_dict_empty_dict(self):
        assert _coerce_dict({}) == {}

    def test_coerce_dict_empty_string(self):
        assert _coerce_dict("") == {}

    def test_coerce_dict_invalid_json(self):
        assert _coerce_dict("not json") == {}

    def test_coerce_dict_non_string_non_dict(self):
        assert _coerce_dict(123) == {}

    def test_coerce_dict_values_coerced_to_str(self):
        result = _coerce_dict({"a": 1, "b": True})
        assert result == {"a": "1", "b": "True"}

    # ── _coerce_list ──────────────────────────────────────────────

    def test_coerce_list_already_list(self):
        assert _coerce_list(["a", "b"]) == ["a", "b"]

    def test_coerce_list_none(self):
        assert _coerce_list(None) is None

    def test_coerce_list_json_string(self):
        result = _coerce_list('["a", "b"]')
        assert result == ["a", "b"]

    def test_coerce_list_empty_list(self):
        assert _coerce_list([]) == []

    def test_coerce_list_empty_string(self):
        assert _coerce_list("") == []

    def test_coerce_list_invalid_json(self):
        assert _coerce_list("not json") == []

    def test_coerce_list_non_string_non_list(self):
        assert _coerce_list(123) == []

    def test_coerce_list_values_coerced_to_str(self):
        result = _coerce_list([1, True])
        assert result == ["1", "True"]

    # ── _parse_json_dict ──────────────────────────────────────────

    def test_parse_json_dict_none(self):
        assert _parse_json_dict(None) == {}

    def test_parse_json_dict_empty(self):
        assert _parse_json_dict("") == {}

    def test_parse_json_dict_normal(self):
        assert _parse_json_dict('{"a": "b"}') == {"a": "b"}

    def test_parse_json_dict_double_encoded(self):
        """Handle the original bug: json.dumps of a JSON string → double encoding."""
        assert _parse_json_dict('"{\\"ChatInput\\": \\"function\\"}"') == {"ChatInput": "function"}

    def test_parse_json_dict_not_a_dict(self):
        assert _parse_json_dict('"plain string"') == {}

    def test_parse_json_dict_bare_string_that_looks_like_json(self):
        """A string that happens to be parseable as JSON, but is not inside quotes."""
        assert _parse_json_dict('{"a": "b"}') == {"a": "b"}

    # ── _parse_json_list ──────────────────────────────────────────

    def test_parse_json_list_none(self):
        assert _parse_json_list(None) == []

    def test_parse_json_list_empty(self):
        assert _parse_json_list("") == []

    def test_parse_json_list_normal(self):
        assert _parse_json_list('["a", "b"]') == ["a", "b"]

    def test_parse_json_list_double_encoded(self):
        assert _parse_json_list('"[\\"a\\", \\"b\\"]"') == ["a", "b"]

    def test_parse_json_list_not_a_list(self):
        assert _parse_json_list('"plain string"') == []


class TestEndpointCoercion:
    """End-to-end: LLM sends string-encoded exports/depends_on, tool handles it."""

    def test_add_string_exports(self, tool, temp_file):
        """Simulate what the LLM sends: exports as a JSON-encoded string."""
        result = asyncio.run(
            tool.run({
                "operation": "add",
                "file_path": temp_file,
                "message": "test file",
                "exports": '{"MyClass": "class", "my_func": "function"}',
            })
        )
        assert "Tagged" in result
        tag = tool._repo.get(os.path.realpath(temp_file))
        assert tag is not None
        assert tag.exports == {"MyClass": "class", "my_func": "function"}

    def test_add_string_depends_on(self, tool, temp_file):
        """Simulate LLM sending depends_on as a JSON-encoded string."""
        result = asyncio.run(
            tool.run({
                "operation": "add",
                "file_path": temp_file,
                "message": "test file",
                "depends_on": '["redis", "database.session"]',
            })
        )
        assert "Tagged" in result
        tag = tool._repo.get(os.path.realpath(temp_file))
        assert tag is not None
        assert tag.depends_on == ["redis", "database.session"]

    def test_add_string_exports_and_depends_on_together(self, tool, temp_file):
        """Both string-encoded structured fields at once."""
        asyncio.run(
            tool.run({
                "operation": "add",
                "file_path": temp_file,
                "message": "full test",
                "exports": '{"Handler": "class"}',
                "depends_on": '["os", "sys"]',
            })
        )
        tag = tool._repo.get(os.path.realpath(temp_file))
        assert tag is not None
        assert tag.exports == {"Handler": "class"}
        assert tag.depends_on == ["os", "sys"]

    def test_update_string_exports(self, tool, temp_file):
        """Update with exports as a string should also be coerced."""
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "message": "base"}))
        result = asyncio.run(
            tool.run({
                "operation": "update",
                "file_path": temp_file,
                "exports": '{"NewClass": "class"}',
            })
        )
        assert "Updated tag" in result
        tag = tool._repo.get(os.path.realpath(temp_file))
        assert tag is not None
        assert tag.exports == {"NewClass": "class"}

    def test_batch_string_exports(self, tool, temp_dir):
        """Batch with exports as a string should work."""
        api_py = Path(temp_dir) / "api.py"
        result = asyncio.run(
            tool.run({
                "operation": "batch",
                "tags": [{
                    "file_path": str(api_py),
                    "message": "API handler",
                    "exports": '{"handle_request": "function"}',
                }],
            })
        )
        assert "Batch processed 1 tag(s)" in result
        tag = tool._repo.get(str(api_py))
        assert tag is not None
        assert tag.exports == {"handle_request": "function"}

    def test_update_string_depends_on(self, tool, temp_file):
        """Update with depends_on as a string should be coerced."""
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "message": "base"}))
        result = asyncio.run(
            tool.run({
                "operation": "update",
                "file_path": temp_file,
                "depends_on": '["libfoo", "libbar"]',
            })
        )
        assert "Updated tag" in result
        tag = tool._repo.get(os.path.realpath(temp_file))
        assert tag is not None
        assert tag.depends_on == ["libfoo", "libbar"]

    def test_double_encoded_data_read_defensively(self, repo):
        """Simulate the exact bug: double-encoded exports in the database.

        If data was already corrupted by the bug, FileTagRepo.get must
        still parse it correctly via _parse_json_dict.
        """
        repo.upsert("/tmp/double_encoded.py", message="buggy", exports='{"ChatInput": "function"}')
        repo.commit()

        # Manually double-encode in the DB (simulate the old bug)
        repo.connection.execute(
            "UPDATE file_tag SET exports=? WHERE path=?",
            (json.dumps('{"ChatInput": "function"}'), "/tmp/double_encoded.py"),
        )
        repo.commit()

        # Reading back must NOT crash with pydantic ValidationError
        tag = repo.get("/tmp/double_encoded.py")
        assert tag is not None
        assert tag.exports == {"ChatInput": "function"}
