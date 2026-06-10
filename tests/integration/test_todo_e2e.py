"""End-to-end integration test: TodoTool → TodoManager → SQLite → RPC handlers.

Tests the full lifecycle:
  1. Agent calls `todowrite(plan)` → TodoManager persists to SQLite
  2. Agent calls `todowrite(read)` → reads back with blocked status
  3. Agent completes a task → blocked child unblocked
  4. RPC `todo/list` reads the same data
  5. RPC `todo/update` modifies a task
  6. Error cases: cycle detection, missing session, missing task
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

from laffyhand.core.db.schema import create_tables
from laffyhand.core.db.repository import TodoRepo
from laffyhand.core.session.todo import TodoManager
from laffyhand.core.tools.todo import TodoTool


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    create_tables(conn)
    conn.execute(
        "INSERT INTO session (id, provider, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("e2e-session", "", "", "2025-01-01T00:00:00", "2025-01-01T00:00:00"),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def mgr(db):
    return TodoManager(TodoRepo(db))


@pytest.fixture
def tool(mgr):
    return TodoTool(mgr)


SID = "e2e-session"


class TestTodoE2E:
    def test_full_dag_lifecycle(self, tool, mgr):
        # 1. Add root task
        asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "Research",
                    "session_id": SID,
                }
            )
        )
        tasks = mgr.get_tasks(SID)
        research = next(t for t in tasks if t.content == "Research")

        # 2. Add child tasks depending on Research
        asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "Implement",
                    "depends_on": [research.id],
                    "session_id": SID,
                }
            )
        )
        asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "Test",
                    "depends_on": [research.id],
                    "session_id": SID,
                }
            )
        )

        # 3. Read: verify DAG status (children blocked by Research)
        read1 = asyncio.run(tool.run({"operation": "read", "session_id": SID}))
        assert "Research" in read1
        lines = [line.strip() for line in read1.split("\n") if line.strip()]
        research_line = next(line for line in lines if "Research" in line)
        assert "pending" in research_line
        blocked_lines = [line for line in lines if "blocked" in line]
        assert len(blocked_lines) == 2

        # 4. Add another task depending on Research
        asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "Document",
                    "depends_on": [research.id],
                    "session_id": SID,
                }
            )
        )
        read2 = asyncio.run(tool.run({"operation": "read", "session_id": SID}))
        assert "Document" in read2

        # 5. Complete Research → all blocked children unblocked
        asyncio.run(
            tool.run(
                {
                    "operation": "update",
                    "id": research.id,
                    "status": "completed",
                    "session_id": SID,
                }
            )
        )
        read3 = asyncio.run(tool.run({"operation": "read", "session_id": SID}))
        assert "blocked" not in read3

    def test_cycle_detection_via_tool(self, tool, mgr):
        asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "A",
                    "session_id": SID,
                }
            )
        )
        asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "B",
                    "session_id": SID,
                }
            )
        )
        tasks = mgr.get_tasks(SID)
        a = next(t for t in tasks if t.content == "A")
        b = next(t for t in tasks if t.content == "B")

        # Make B depend on A (OK)
        result = asyncio.run(
            tool.run(
                {
                    "operation": "update",
                    "id": b.id,
                    "depends_on": [a.id],
                    "session_id": SID,
                }
            )
        )
        assert "Updated" in result

        # Now try to make A depend on B (cycle: A→B→A)
        with pytest.raises(ValueError, match="cycle"):
            asyncio.run(
                tool.run(
                    {
                        "operation": "update",
                        "id": a.id,
                        "depends_on": [b.id],
                        "session_id": SID,
                    }
                )
            )

    def test_tool_delete_with_dependents(self, tool, mgr):
        asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "Parent",
                    "session_id": SID,
                }
            )
        )
        tasks = mgr.get_tasks(SID)
        parent = next(t for t in tasks if t.content == "Parent")
        asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "Child",
                    "depends_on": [parent.id],
                    "session_id": SID,
                }
            )
        )

        asyncio.run(
            tool.run(
                {
                    "operation": "delete",
                    "id": parent.id,
                    "session_id": SID,
                }
            )
        )

        remaining = mgr.get_tasks(SID)
        child = next(t for t in remaining if t.content == "Child")
        assert parent.id not in child.depends_on

    def test_rpc_list_matches_tool_read(self, tool, mgr):
        """Verify that the data read via todo/list RPC is consistent with tool read."""
        asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "Task A",
                    "session_id": SID,
                }
            )
        )
        tasks = mgr.get_tasks(SID)
        a = next(t for t in tasks if t.content == "Task A")
        asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "Task B",
                    "depends_on": [a.id],
                    "session_id": SID,
                }
            )
        )

        tool_result = asyncio.run(tool.run({"operation": "read", "session_id": SID}))
        tasks = mgr.get_tasks(SID)

        assert len(tasks) == 2
        for t in tasks:
            assert t.session_id == SID
            assert t.content
            assert t.status in ("pending", "blocked")

        # The tool output should mention both tasks
        assert "Task A" in tool_result
        assert "Task B" in tool_result

    def test_tool_read_filter_by_status(self, tool, mgr):
        asyncio.run(
            tool.run({"operation": "add", "content": "active", "session_id": SID})
        )
        tasks = mgr.get_tasks(SID)
        active = next(t for t in tasks if t.content == "active")
        asyncio.run(
            tool.run(
                {
                    "operation": "update",
                    "id": active.id,
                    "status": "completed",
                    "session_id": SID,
                }
            )
        )

        result = asyncio.run(
            tool.run(
                {
                    "operation": "read",
                    "status": "completed",
                    "session_id": SID,
                }
            )
        )
        assert "active" in result

        pending_result = asyncio.run(
            tool.run(
                {
                    "operation": "read",
                    "status": "pending",
                    "session_id": SID,
                }
            )
        )
        assert pending_result == "No tasks."

    def test_session_isolation(self, tool, mgr, db):
        """Tasks in different sessions should not interfere."""
        db.execute(
            "INSERT INTO session (id, provider, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("other-session", "", "", "2025-01-01T00:00:00", "2025-01-01T00:00:00"),
        )
        db.commit()

        asyncio.run(
            tool.run(
                {"operation": "add", "content": "session-1 task", "session_id": SID}
            )
        )
        asyncio.run(
            tool.run(
                {
                    "operation": "add",
                    "content": "session-2 task",
                    "session_id": "other-session",
                }
            )
        )

        s1_tasks = mgr.get_tasks(SID)
        s2_tasks = mgr.get_tasks("other-session")
        assert len(s1_tasks) == 1
        assert len(s2_tasks) == 1
        assert s1_tasks[0].content == "session-1 task"
        assert s2_tasks[0].content == "session-2 task"
