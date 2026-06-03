import asyncio
import sqlite3
import pytest

from laffyhand.agent.session.todo import TodoManager
from laffyhand.agent.db.repository import TodoRepo
from laffyhand.agent.db.schema import create_tables
from laffyhand.agent.tools.todo import TodoTool


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
def session_id():
    return "test-session"


@pytest.fixture
def manager(db, session_id):
    db.execute(
        "INSERT INTO session (id, provider, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, "", "", "2025-01-01T00:00:00", "2025-01-01T00:00:00"),
    )
    db.commit()
    return TodoManager(TodoRepo(db))


@pytest.fixture
def tool(manager):
    return TodoTool(manager)


class TestTodoTool:
    def test_read_empty(self, tool, session_id):
        result = asyncio.run(tool.run({"operation": "read", "session_id": session_id}))
        assert "No tasks" in result

    def test_add_and_read(self, tool, session_id):
        asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "test task",
                    "priority": "high",
                    "session_id": session_id,
                }
            )
        )
        result = asyncio.run(tool.run({"operation": "read", "session_id": session_id}))
        assert "test task" in result
        assert "high" in result

    def test_add_requires_content(self, tool, session_id):
        result = asyncio.run(tool.run({"operation": "add", "session_id": session_id}))
        assert "content is required" in result

    def test_plan(self, tool, session_id):
        result = asyncio.run(
            tool.run(
                {
                    "operation": "plan",
                    "tasks": [
                        {"id": "t1", "content": "Task 1"},
                        {"id": "t2", "content": "Task 2", "depends_on": ["t1"]},
                    ],
                    "session_id": session_id,
                }
            )
        )
        assert "Planned 2 task(s)" in result

    def test_plan_empty_tasks_returns_error(self, tool, session_id):
        result = asyncio.run(
            tool.run({"operation": "plan", "tasks": [], "session_id": session_id})
        )
        assert "tasks list is required" in result

    def test_plan_missing_tasks_field_returns_error(self, tool, session_id):
        result = asyncio.run(tool.run({"operation": "plan", "session_id": session_id}))
        assert "tasks list is required" in result

    def test_update_status(self, tool, session_id):
        asyncio.run(
            tool.run({"operation": "add", "content": "task", "session_id": session_id})
        )
        tasks = asyncio.run(tool.run({"operation": "read", "session_id": session_id}))
        task_id = tasks.split("\n")[0].split()[0]
        result = asyncio.run(
            tool.run(
                {
                    "operation": "update",
                    "id": task_id,
                    "status": "completed",
                    "session_id": session_id,
                }
            )
        )
        assert "completed" in result

    def test_update_requires_id(self, tool, session_id):
        result = asyncio.run(
            tool.run({"operation": "update", "session_id": session_id})
        )
        assert "id or ids is required" in result

    def test_update_nonexistent_returns_error(self, tool, session_id):
        result = asyncio.run(
            tool.run(
                {
                    "operation": "update",
                    "id": "no-such",
                    "status": "completed",
                    "session_id": session_id,
                }
            )
        )
        assert "not found" in result

    def test_update_with_content_and_priority(self, tool, session_id):
        asyncio.run(
            tool.run({"operation": "add", "content": "old", "session_id": session_id})
        )
        tasks = asyncio.run(tool.run({"operation": "read", "session_id": session_id}))
        task_id = tasks.split("\n")[0].split()[0]
        result = asyncio.run(
            tool.run(
                {
                    "operation": "update",
                    "id": task_id,
                    "content": "new content",
                    "priority": "high",
                    "session_id": session_id,
                }
            )
        )
        assert "high" in result

    def test_delete(self, tool, session_id):
        asyncio.run(
            tool.run({"operation": "add", "content": "task", "session_id": session_id})
        )
        tasks = asyncio.run(tool.run({"operation": "read", "session_id": session_id}))
        task_id = tasks.split("\n")[0].split()[0]
        asyncio.run(
            tool.run({"operation": "delete", "id": task_id, "session_id": session_id})
        )
        result = asyncio.run(tool.run({"operation": "read", "session_id": session_id}))
        assert "No tasks" in result

    def test_delete_unknown(self, tool, session_id):
        result = asyncio.run(
            tool.run({"operation": "delete", "id": "999", "session_id": session_id})
        )
        assert "not found" in result

    def test_unknown_operation(self, tool, session_id):
        result = asyncio.run(
            tool.run({"operation": "unknown", "session_id": session_id})
        )
        assert "Unknown operation" in result

    def test_read_with_status_filter(self, tool, session_id):
        asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "task1",
                    "session_id": session_id,
                    "priority": "high",
                }
            )
        )
        tasks = asyncio.run(tool.run({"operation": "read", "session_id": session_id}))
        task_id = tasks.split("\n")[0].split()[0]
        asyncio.run(
            tool.run(
                {
                    "operation": "update",
                    "id": task_id,
                    "status": "completed",
                    "session_id": session_id,
                }
            )
        )
        result = asyncio.run(
            tool.run(
                {"operation": "read", "session_id": session_id, "status": "completed"}
            )
        )
        assert "task1" in result

    def test_dag_plan_blocked_status_appears_in_read(self, tool, session_id):
        asyncio.run(
            tool.run(
                {
                    "operation": "plan",
                    "tasks": [
                        {"id": "t1", "content": "Parent task"},
                        {"id": "t2", "content": "Child task", "depends_on": ["t1"]},
                    ],
                    "session_id": session_id,
                }
            )
        )
        result = asyncio.run(tool.run({"operation": "read", "session_id": session_id}))
        assert "blocked" in result

    def test_requires_session_id(self, tool):
        result = asyncio.run(tool.run({"operation": "read"}))
        assert "session_id is required" in result

    def test_add_with_depends_on(self, tool, session_id):
        asyncio.run(
            tool.run(
                {"operation": "add", "content": "parent", "session_id": session_id}
            )
        )
        tasks = asyncio.run(tool.run({"operation": "read", "session_id": session_id}))
        parent_id = tasks.split("\n")[0].split()[0]
        result = asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "child",
                    "depends_on": [parent_id],
                    "session_id": session_id,
                }
            )
        )
        assert "Added" in result
        r2 = asyncio.run(tool.run({"operation": "read", "session_id": session_id}))
        assert "blocked" in r2

    def test_completing_task_unblocks_dependents(self, tool, session_id):
        asyncio.run(
            tool.run(
                {"operation": "add", "content": "parent", "session_id": session_id}
            )
        )
        tasks = asyncio.run(tool.run({"operation": "read", "session_id": session_id}))
        parent_id = tasks.split("\n")[0].split()[0]
        asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "child",
                    "depends_on": [parent_id],
                    "session_id": session_id,
                }
            )
        )
        r1 = asyncio.run(tool.run({"operation": "read", "session_id": session_id}))
        assert "blocked" in r1

        asyncio.run(
            tool.run(
                {
                    "operation": "update",
                    "id": parent_id,
                    "status": "completed",
                    "session_id": session_id,
                }
            )
        )
        r2 = asyncio.run(tool.run({"operation": "read", "session_id": session_id}))
        assert "blocked" not in r2
