from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from laffyhand.db import FileTagRepo, create_tables
from laffyhand.core.models.tag import FileTag
from laffyhand.core.tools.tag import TagTool, annotate_result, format_tag_summary, _normalize, _date_from_iso


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
    d = Path(tempfile.mkdtemp())
    yield d
    for f in sorted(d.rglob("*"), reverse=True):
        if f.is_file():
            f.unlink()
        else:
            try:
                f.rmdir()
            except OSError:
                pass
    try:
        d.rmdir()
    except OSError:
        pass


class TestFileTagRepo:
    def test_upsert_and_get(self, repo):
        repo.upsert("/tmp/test.py", content="test file")
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.path == "/tmp/test.py"
        assert tag.content == "test file"

    def test_upsert_updates_existing(self, repo):
        repo.upsert("/tmp/test.py", content="old")
        repo.upsert("/tmp/test.py", content="new")
        tag = repo.get("/tmp/test.py")
        assert tag is not None
        assert tag.content == "new"

    def test_get_nonexistent(self, repo):
        assert repo.get("/tmp/nonexistent.py") is None

    def test_list_by_prefix(self, repo):
        repo.upsert("/tmp/a.py", content="a")
        repo.upsert("/tmp/b.py", content="b")
        repo.upsert("/other/c.py", content="c")
        tags = repo.list_by_prefix("/tmp/")
        assert len(tags) == 2

    def test_list_all(self, repo):
        repo.upsert("/tmp/a.py", content="a")
        repo.upsert("/tmp/b.py", content="b")
        tags = repo.list_all()
        assert len(tags) == 2

    def test_delete(self, repo):
        repo.upsert("/tmp/test.py", content="test")
        assert repo.delete("/tmp/test.py") is True
        assert repo.get("/tmp/test.py") is None

    def test_delete_nonexistent(self, repo):
        assert repo.delete("/tmp/nonexistent.py") is False

class TestTagTool:
    def test_add(self, tool, temp_file):
        result = asyncio.run(
            tool.run({"operation": "add", "file_path": temp_file, "content": "test file", "session_id": "x"})
        )
        assert "Tagged" in result

    def test_add_requires_file(self, tool):
        result = asyncio.run(
            tool.run({"operation": "add", "content": "test", "session_id": "x"})
        )
        assert "file_path" in result

    def test_add_requires_content(self, tool, temp_file):
        result = asyncio.run(
            tool.run({"operation": "add", "file_path": temp_file, "session_id": "x"})
        )
        assert "content" in result

    def test_add_nonexistent_path(self, tool):
        result = asyncio.run(
            tool.run({"operation": "add", "file_path": "/nonexistent/path.py", "content": "test", "session_id": "x"})
        )
        assert "not exist" in result

    def test_update(self, tool, temp_file):
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "content": "old", "session_id": "x"}))
        result = asyncio.run(
            tool.run({"operation": "update", "file_path": temp_file, "content": "new", "session_id": "x"})
        )
        assert "Updated tag" in result

    def test_update_requires_file(self, tool):
        result = asyncio.run(
            tool.run({"operation": "update", "content": "new", "session_id": "x"})
        )
        assert "file_path" in result

    def test_list_all(self, tool, temp_file, temp_dir):
        asyncio.run(tool.run({"operation": "add", "file_path": temp_file, "content": "a", "session_id": "x"}))
        result = asyncio.run(tool.run({"operation": "list", "session_id": "x"}))
        assert "Found" in result

    def test_list_empty(self, tool):
        result = asyncio.run(tool.run({"operation": "list", "session_id": "x"}))
        assert "No tags" in result

    def test_path_normalization(self, tool, temp_file):
        result = asyncio.run(
            tool.run({"operation": "add", "file_path": temp_file, "content": "test", "session_id": "x"})
        )
        assert "Tagged" in result

    def test_unknown_operation(self, tool):
        result = asyncio.run(tool.run({"operation": "unknown", "session_id": "x"}))
        assert "Unknown operation" in result

    def test_batch_add(self, tool, temp_dir):
        f1 = temp_dir / "a.py"
        f1.write_text("a")
        f2 = temp_dir / "b.py"
        f2.write_text("b")
        result = asyncio.run(
            tool.run({
                "operation": "batch",
                "tags": [{"file_path": str(f1), "content": "file a"}, {"file_path": str(f2), "content": "file b"}],
                "session_id": "x",
            })
        )
        assert "Batch processed 2 tag(s)" in result


class TestAnnotation:
    @pytest.fixture
    def repo_with_tags(self, repo, temp_dir):
        for name in ["a.py", "b.py", "sub"]:
            p = temp_dir / name
            if name == "sub":
                p.mkdir()
            else:
                p.write_text("content")
            repo.upsert(str(p), content=f"file {name}")
        repo.commit()
        return repo, temp_dir

    def test_annotate_glob(self, repo_with_tags):
        repo, temp_dir = repo_with_tags
        result = annotate_result("glob", f"{temp_dir / 'a.py'}", {"path": str(temp_dir), "show_tags": True}, repo)
        assert "file a.py" in result

    def test_annotate_glob_no_tags(self, repo_with_tags):
        repo, temp_dir = repo_with_tags
        result = annotate_result("glob", f"{temp_dir / 'a.py'}", {"path": str(temp_dir), "show_tags": True}, repo)
        assert result.strip() != ""

    def test_annotate_read_directory(self, repo_with_tags):
        repo, temp_dir = repo_with_tags
        result = annotate_result("list_dir", f"Contents of {temp_dir}:\n  a.py\n  b.py\n", {"file_path": str(temp_dir), "show_tags": True}, repo)
        assert "a.py" in result

    def test_annotate_read_no_tags(self, repo_with_tags):
        repo, temp_dir = repo_with_tags
        result = annotate_result("list_dir", f"Contents of {temp_dir}:\n  a.py\n", {"file_path": str(temp_dir), "show_tags": False}, repo)
        assert "a.py" in result

    def test_annotate_other_tool(self, repo_with_tags):
        repo, temp_dir = repo_with_tags
        result = annotate_result("read", "some content", {"show_tags": True}, repo)
        assert "some content" in result

    def test_annotate_empty_result(self, repo_with_tags):
        repo, temp_dir = repo_with_tags
        assert annotate_result("glob", "", {"show_tags": True}, repo) == ""

    def test_annotate_glob_show_tags_false(self, repo_with_tags):
        repo, temp_dir = repo_with_tags
        path = temp_dir / "a.py"
        result = annotate_result("glob", str(path), {"path": str(temp_dir), "show_tags": False}, repo)
        assert result.strip() == str(path)


class TestHelpers:
    def test_normalize(self):
        assert _normalize("/tmp/test.py") == os.path.realpath("/tmp/test.py")

    def test_date_from_iso(self):
        assert _date_from_iso("2025-01-01T12:00:00") == "2025-01-01"

    def test_format_tag_summary(self):
        tag = FileTag(path="/tmp/test.py", content="test file", updated_at="2025-01-01T12:00:00")
        result = format_tag_summary(tag)
        assert "test file" in result
        assert "2025-01-01" in result

    def test_format_tag_summary_no_truncation(self):
        tag = FileTag(path="/tmp/test.py", content="a" * 200, updated_at="2025-01-01T12:00:00")
        result = format_tag_summary(tag)
        assert "a" * 200 in result
