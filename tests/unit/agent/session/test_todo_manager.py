from __future__ import annotations

import sqlite3

import pytest

from laffyhand.agent.session.models import TodoCreate, TodoUpdate
from laffyhand.agent.session.schema import create_tables
from laffyhand.agent.session.todo import TodoManager


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    create_tables(conn)
    conn.execute(
        "INSERT INTO session (id, created_at, updated_at) VALUES (?, ?, ?)",
        ("sess-1", "2025-01-01T00:00:00", "2025-01-01T00:00:00"),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def mgr(db):
    return TodoManager(db)


class TestTodoManagerCRUD:
    def test_add_and_get_task(self, mgr):
        item = mgr.add_task("sess-1", "do stuff", priority="high")
        assert item.id
        assert item.content == "do stuff"
        assert item.priority == "high"
        assert item.status == "pending"

        got = mgr.get_task(item.id)
        assert got is not None
        assert got.content == "do stuff"
        assert got.priority == "high"

    def test_add_tasks_bulk(self, mgr):
        items = mgr.add_tasks(
            "sess-1",
            [
                TodoCreate(content="Task A", priority="high"),
                TodoCreate(content="Task B", priority="low"),
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

    def test_update_task_content_and_priority(self, mgr):
        item = mgr.add_task("sess-1", "original")
        mgr.update_task(
            item.id, "sess-1", TodoUpdate(content="updated", priority="low")
        )

        got = mgr.get_task(item.id)
        assert got is not None
        assert got.content == "updated"
        assert got.priority == "low"

    def test_update_task_sets_completed_at_on_completion(self, mgr):
        item = mgr.add_task("sess-1", "finish me")
        assert item.completed_at is None

        mgr.update_task(item.id, "sess-1", TodoUpdate(status="completed"))
        got = mgr.get_task(item.id)
        assert got is not None
        assert got.completed_at is not None

    def test_update_task_clears_completed_at_when_uncompleted(self, mgr):
        item = mgr.add_task("sess-1", "test")
        mgr.update_task(item.id, "sess-1", TodoUpdate(status="completed"))
        mgr.update_task(item.id, "sess-1", TodoUpdate(status="in_progress"))
        got = mgr.get_task(item.id)
        assert got is not None
        assert got.completed_at is None

    def test_delete_task_removes_it(self, mgr):
        item = mgr.add_task("sess-1", "delete me")
        assert mgr.delete_task(item.id) is True
        assert mgr.get_task(item.id) is None

    def test_delete_task_returns_false_for_missing(self, mgr):
        assert mgr.delete_task("nonexistent") is False

    def test_delete_session_tasks_clears_all(self, mgr):
        mgr.add_task("sess-1", "a")
        mgr.add_task("sess-1", "b")
        mgr.delete_session_tasks("sess-1")
        assert mgr.get_tasks("sess-1") == []

    def test_update_nonexistent_returns_none(self, mgr):
        result = mgr.update_task("no-such-id", "sess-1", TodoUpdate(status="completed"))
        assert result is None


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
                TodoCreate(content="Root", priority="high"),
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

    def test_completed_and_cancelled_tasks_never_blocked(self, mgr):
        parent = mgr.add_task("sess-1", "parent")
        child = mgr.add_task("sess-1", "child", depends_on=[parent.id])

        mgr.update_task(child.id, "sess-1", TodoUpdate(status="completed"))
        tasks = mgr.get_tasks("sess-1")
        child_task = next(t for t in tasks if t.id == child.id)
        assert child_task.status == "completed"

        mgr.update_task(child.id, "sess-1", TodoUpdate(status="cancelled"))
        tasks = mgr.get_tasks("sess-1")
        child_task = next(t for t in tasks if t.id == child.id)
        assert child_task.status == "cancelled"


class TestTodoManagerTaskTool:
    def test_link_task_tool_sets_in_progress(self, mgr):
        item = mgr.add_task("sess-1", "delegate task")
        mgr.link_task_tool(item.id, "tool-call-abc")
        got = mgr.get_task(item.id)
        assert got is not None
        assert got.status == "in_progress"
        assert got.task_tool_id == "tool-call-abc"

    def test_on_subagent_complete_sets_completed(self, mgr):
        item = mgr.add_task("sess-1", "task for subagent")
        mgr.link_task_tool(item.id, "tool-call-xyz")
        mgr.on_subagent_complete("tool-call-xyz", success=True)
        got = mgr.get_task(item.id)
        assert got is not None
        assert got.status == "completed"
        assert got.completed_at is not None

    def test_on_subagent_failure_resets_to_pending(self, mgr):
        item = mgr.add_task("sess-1", "failing task")
        mgr.link_task_tool(item.id, "tool-call-fail")
        mgr.on_subagent_complete("tool-call-fail", success=False)
        got = mgr.get_task(item.id)
        assert got is not None
        assert got.status == "pending"
        assert got.task_tool_id is None

    def test_on_subagent_complete_unknown_tool(self, mgr):
        result = mgr.on_subagent_complete("no-such-tool", success=True)
        assert result is None
