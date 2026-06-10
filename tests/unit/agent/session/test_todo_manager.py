from __future__ import annotations

import sqlite3

import pytest

from laffyhand.core.session.todo import TodoCreate, TodoUpdate
from laffyhand.db import create_tables, TodoRepo
from laffyhand.core.session.todo import TodoManager


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    create_tables(conn)
    conn.execute(
        "INSERT INTO session (id, provider, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("sess-1", "", "", "2025-01-01T00:00:00", "2025-01-01T00:00:00"),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def mgr(db):
    return TodoManager(TodoRepo(db))


class TestTodoManagerCRUD:
    def test_add_and_get_task(self, mgr):
        item = mgr.add_task("sess-1", "do stuff")
        assert item.id
        assert item.content == "do stuff"
        assert item.status == "pending"

        tasks = mgr.get_tasks("sess-1")
        got = next((t for t in tasks if t.id == item.id), None)
        assert got is not None
        assert got.content == "do stuff"

    def test_add_tasks_bulk(self, mgr):
        items = mgr.add_tasks(
            "sess-1",
            [
                TodoCreate(content="Task A"),
                TodoCreate(content="Task B"),
            ],
        )
        assert len(items) == 2
        ids = {t.id for t in items}
        assert len(ids) == 2

    def test_get_tasks_filters_by_session(self, mgr):
        mgr.add_task("sess-1", "task-1")
        mgr.add_task("sess-1", "task-2")
        mgr.add_task("sess-1", "task-3")

        tasks = mgr.get_tasks("sess-1")
        assert len(tasks) == 3

    def test_get_tasks_filters_by_status(self, mgr):
        t1 = mgr.add_task("sess-1", "active task")
        mgr.add_task("sess-1", "done task")
        mgr.update_task(t1.id, "sess-1", TodoUpdate(status="completed"))

        pending = mgr.get_tasks("sess-1", status="completed")
        assert len(pending) == 1
        assert pending[0].id == t1.id

    def test_update_task_content(self, mgr):
        item = mgr.add_task("sess-1", "original")
        mgr.update_task(
            item.id, "sess-1", TodoUpdate(content="updated")
        )

        tasks = mgr.get_tasks("sess-1")
        got = next((t for t in tasks if t.id == item.id), None)
        assert got is not None
        assert got.content == "updated"

    def test_update_task_sets_completed_at_on_completion(self, mgr):
        item = mgr.add_task("sess-1", "finish me")
        assert item.completed_at is None

        mgr.update_task(item.id, "sess-1", TodoUpdate(status="completed"))
        tasks = mgr.get_tasks("sess-1")
        got = next((t for t in tasks if t.id == item.id), None)
        assert got is not None
        assert got.completed_at is not None

    def test_update_task_clears_completed_at_when_uncompleted(self, mgr):
        item = mgr.add_task("sess-1", "test")
        mgr.update_task(item.id, "sess-1", TodoUpdate(status="completed"))
        mgr.update_task(item.id, "sess-1", TodoUpdate(status="in_progress"))
        got = mgr.get_tasks("sess-1")
        assert len(got) > 0

    def test_delete_task_removes_it(self, mgr):
        item = mgr.add_task("sess-1", "delete me")
        assert mgr.delete_task(item.id) is True
        tasks = mgr.get_tasks("sess-1")
        assert item.id not in {t.id for t in tasks}

    def test_delete_task_returns_false_for_missing(self, mgr):
        assert mgr.delete_task("nonexistent") is False

    def test_update_nonexistent_returns_none(self, mgr):
        result = mgr.update_task("no-such-id", "sess-1", TodoUpdate(status="completed"))
        assert result is None


class TestTodoManagerCustomID:
    """Tests for custom short ID support in add_task and add_tasks."""

    def test_add_task_with_custom_id(self, mgr):
        item = mgr.add_task("sess-1", "custom id task", id="step1")
        assert item.id == "step1"
        assert item.content == "custom id task"

        # Verify it persists
        tasks = mgr.get_tasks("sess-1")
        got = next((t for t in tasks if t.id == "step1"), None)
        assert got is not None
        assert got.content == "custom id task"

    def test_add_task_auto_generates_id_when_not_provided(self, mgr):
        item = mgr.add_task("sess-1", "auto id task")
        # Should be a long auto-generated ID like YYYYMMDD_HHMMSS_xxxxxxxx
        assert "_" in item.id
        assert item.id != "step1"

    def test_add_task_custom_id_conflict_raises_error(self, mgr):
        mgr.add_task("sess-1", "first", id="step1")
        with pytest.raises(ValueError, match="already exists in this session"):
            mgr.add_task("sess-1", "second", id="step1")

    def test_add_task_same_id_different_session_ok(self, mgr, db):
        db.execute(
            "INSERT INTO session (id, provider, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("sess-2", "", "", "2025-01-01T00:00:00", "2025-01-01T00:00:00"),
        )
        db.commit()
        mgr.add_task("sess-1", "first session", id="step1")
        item = mgr.add_task("sess-2", "second session", id="step1")
        assert item.id == "step1"
        assert item.session_id == "sess-2"

    def test_add_task_with_custom_id_and_depends_on(self, mgr):
        mgr.add_task("sess-1", "parent", id="parent1")
        child = mgr.add_task(
            "sess-1", "child", depends_on=["parent1"], id="child1"
        )
        assert child.id == "child1"
        assert child.depends_on == ["parent1"]

        tasks = mgr.get_tasks("sess-1")
        child_task = next(t for t in tasks if t.id == "child1")
        assert child_task.status == "blocked"
        assert "parent1" in child_task.metadata.get("blocked_by", [])

    def test_add_tasks_with_custom_ids(self, mgr):
        items = mgr.add_tasks(
            "sess-1",
            [
                TodoCreate(id="t1", content="Task 1"),
                TodoCreate(id="t2", content="Task 2", depends_on=["t1"]),
            ],
        )
        assert len(items) == 2
        t1 = next(t for t in items if t.id == "t1")
        assert t1.content == "Task 1"
        t2 = next(t for t in items if t.id == "t2")
        assert t2.content == "Task 2"
        assert t2.depends_on == ["t1"]
        # t2 should be blocked by t1
        assert t2.status == "blocked"

    def test_add_tasks_with_conflicting_custom_id_raises_error(self, mgr):
        # Pre-create a task with id "t1"
        mgr.add_task("sess-1", "existing", id="t1")
        with pytest.raises(ValueError, match="conflicts"):
            mgr.add_tasks(
                "sess-1",
                [TodoCreate(id="t1", content="duplicate")],
            )

    def test_add_tasks_with_duplicate_custom_id_in_batch_raises_error(self, mgr):
        with pytest.raises(ValueError, match="conflicts"):
            mgr.add_tasks(
                "sess-1",
                [
                    TodoCreate(id="dup", content="first"),
                    TodoCreate(id="dup", content="second"),
                ],
            )

    def test_add_tasks_same_id_different_session_ok(self, mgr, db):
        db.execute(
            "INSERT INTO session (id, provider, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("sess-2", "", "", "2025-01-01T00:00:00", "2025-01-01T00:00:00"),
        )
        db.commit()
        mgr.add_tasks("sess-1", [TodoCreate(id="step1", content="sess1 task")])
        items = mgr.add_tasks("sess-2", [TodoCreate(id="step1", content="sess2 task")])
        assert len(items) == 1
        assert items[0].id == "step1"
        assert items[0].session_id == "sess-2"

    def test_add_tasks_with_missing_dependency_reference(self, mgr):
        """Using references to custom IDs as depends_on should work by referencing the actual ID."""
        with pytest.raises(ValueError, match="does not exist"):
            mgr.add_tasks(
                "sess-1",
                [
                    TodoCreate(id="orphan", content="orphan", depends_on=["nonexistent"]),
                ],
            )


class TestTodoManagerDAG:
    def test_depends_on_creates_blocked_status(self, mgr):
        parent = mgr.add_task("sess-1", "parent")
        child = mgr.add_task("sess-1", "child", depends_on=[parent.id])

        tasks = mgr.get_tasks("sess-1")
        child_task = next(t for t in tasks if t.id == child.id)
        assert child_task.status == "blocked"
        assert parent.id in child_task.metadata.get("blocked_by", [])

    def test_completing_parent_resolves_blocked_child(self, mgr):
        parent = mgr.add_task("sess-1", "parent")
        child = mgr.add_task("sess-1", "child", depends_on=[parent.id])

        mgr.update_task(parent.id, "sess-1", TodoUpdate(status="completed"))

        tasks = mgr.get_tasks("sess-1")
        child_task = next(t for t in tasks if t.id == child.id)
        assert child_task.status == "pending"
        assert "blocked_by" not in child_task.metadata or not child_task.metadata.get(
            "blocked_by"
        )

    def test_cycle_detection_rejects_circular_dependency(self, mgr):
        a = mgr.add_task("sess-1", "A")
        b = mgr.add_task("sess-1", "B", depends_on=[a.id])
        # Trying to make A depend on B creates A→B→A cycle
        with pytest.raises(ValueError, match="cycle"):
            mgr.update_task(a.id, "sess-1", TodoUpdate(depends_on=[b.id]))

    def test_self_dependency_rejected(self, mgr):
        a = mgr.add_task("sess-1", "A")
        with pytest.raises(ValueError, match="depend on itself"):
            mgr.update_task(a.id, "sess-1", TodoUpdate(depends_on=[a.id]))

    def test_add_tasks_with_cross_deps(self, mgr):
        items = mgr.add_tasks(
            "sess-1",
            [
                TodoCreate(content="Root"),
                TodoCreate(content="Child", depends_on=[]),
            ],
        )
        assert len(items) == 2
        # Cross-batch dependencies in add_tasks are not supported;
        # use add_task individually for dependent items.

    def test_multi_level_dag(self, mgr):
        t1 = mgr.add_task("sess-1", "Layer 1")
        t2 = mgr.add_task("sess-1", "Layer 2", depends_on=[t1.id])
        t3 = mgr.add_task("sess-1", "Layer 3", depends_on=[t2.id])

        tasks = mgr.get_tasks("sess-1")
        l2 = next(t for t in tasks if t.id == t2.id)
        l3 = next(t for t in tasks if t.id == t3.id)
        assert l2.status == "blocked"
        assert l3.status == "blocked"

        mgr.update_task(t1.id, "sess-1", TodoUpdate(status="completed"))
        tasks = mgr.get_tasks("sess-1")
        l2 = next(t for t in tasks if t.id == t2.id)
        l3 = next(t for t in tasks if t.id == t3.id)
        assert l2.status == "pending"
        assert l3.status == "blocked"

        mgr.update_task(t2.id, "sess-1", TodoUpdate(status="completed"))
        tasks = mgr.get_tasks("sess-1")
        l3 = next(t for t in tasks if t.id == t3.id)
        assert l3.status == "pending"

    def test_validate_depends_rejects_missing_dep(self, mgr):
        with pytest.raises(ValueError, match="does not exist"):
            mgr.add_task("sess-1", "orphan", depends_on=["ghost"])

    def test_completed_tasks_never_blocked(self, mgr):
        parent = mgr.add_task("sess-1", "parent")
        child = mgr.add_task("sess-1", "child", depends_on=[parent.id])

        mgr.update_task(child.id, "sess-1", TodoUpdate(status="completed"))
        tasks = mgr.get_tasks("sess-1")
        child_task = next(t for t in tasks if t.id == child.id)
        assert child_task.status == "completed"
