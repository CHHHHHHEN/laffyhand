from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from laffyhand.gateway.handlers import handle_todo_list, handle_todo_update


def _make_task(
    task_id: str,
    content: str = "test",
    status: str = "pending",
    depends_on: list[str] | None = None,
    blocked_by: list[str] | None = None,
):
    """Build a TodoItem-like mock. We patch the return from todo_manager."""
    task = MagicMock()
    task.id = task_id
    task.session_id = "sess-1"
    task.content = content
    task.status = status
    task.depends_on = depends_on or []
    task.created_at.isoformat.return_value = "2025-01-01T00:00:00"
    task.updated_at.isoformat.return_value = "2025-01-01T01:00:00"
    task.completed_at = None
    task.task_tool_id = None
    task.metadata = {"blocked_by": blocked_by or []}
    return task


@pytest.fixture
def runtime():
    r = MagicMock()
    r.current_session_id = "sess-1"
    r.todo_manager = MagicMock()
    return r


@pytest.fixture
def transport():
    t = MagicMock()
    t.send = AsyncMock()
    return t


class TestHandleTodoList:
    @pytest.mark.anyio
    async def test_returns_tasks_for_session(self, runtime, transport):
        runtime.todo_manager.get_tasks.return_value = [
            _make_task("t1", content="Task 1"),
            _make_task("t2", content="Task 2", status="completed"),
        ]
        result = await handle_todo_list(
            runtime, {"session_id": "sess-1"}, transport, 1, "c1"
        )
        assert len(result["tasks"]) == 2
        assert result["tasks"][0]["id"] == "t1"
        assert result["tasks"][0]["content"] == "Task 1"
        assert result["tasks"][1]["status"] == "completed"

    @pytest.mark.anyio
    async def test_filters_by_status(self, runtime, transport):
        runtime.todo_manager.get_tasks.return_value = [
            _make_task("t1", status="completed", content="done"),
        ]
        result = await handle_todo_list(
            runtime, {"session_id": "sess-1", "status": "completed"}, transport, 1, "c1"
        )
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["status"] == "completed"
        runtime.todo_manager.get_tasks.assert_called_once_with(
            "sess-1", status="completed"
        )

    @pytest.mark.anyio
    async def test_empty_list(self, runtime, transport):
        runtime.todo_manager.get_tasks.return_value = []
        result = await handle_todo_list(
            runtime, {"session_id": "sess-1"}, transport, 1, "c1"
        )
        assert result["tasks"] == []

    @pytest.mark.anyio
    async def test_session_id_in_params(self, runtime, transport):
        runtime.todo_manager.get_tasks.return_value = []
        await handle_todo_list(
            runtime, {"session_id": "sess-1"}, transport, 1, "c1"
        )
        runtime.todo_manager.get_tasks.assert_called_once_with("sess-1", status=None)

    @pytest.mark.anyio
    async def test_returns_blocked_by_in_response(self, runtime, transport):
        runtime.todo_manager.get_tasks.return_value = [
            _make_task("t2", content="child", blocked_by=["t1"]),
        ]
        result = await handle_todo_list(
            runtime, {"session_id": "sess-1"}, transport, 1, "c1"
        )
        assert result["tasks"][0]["blockedBy"] == ["t1"]

    @pytest.mark.anyio
    async def test_returned_fields_match_snake_case_mapping(self, runtime, transport):
        task = _make_task(
            "t1",
            content="test task",
            status="completed",
            depends_on=["dep1"],
        )
        runtime.todo_manager.get_tasks.return_value = [task]
        result = await handle_todo_list(
            runtime, {"session_id": "sess-1"}, transport, 1, "c1"
        )
        t = result["tasks"][0]
        assert t["id"] == "t1"
        assert t["sessionId"] == "sess-1"
        assert t["content"] == "test task"
        assert t["status"] == "completed"
        assert t["dependsOn"] == ["dep1"]
        assert t["blockedBy"] == []
        assert t["createdAt"] == "2025-01-01T00:00:00"
        assert t["updatedAt"] == "2025-01-01T01:00:00"
        assert t["completedAt"] is None
        assert t["taskToolId"] is None


class TestHandleTodoUpdate:
    @pytest.mark.anyio
    async def test_updates_task_status(self, runtime, transport):
        runtime.todo_manager.update_task.return_value = _make_task(
            "t1", status="completed"
        )
        result = await handle_todo_update(
            runtime,
            {"task_id": "t1", "status": "completed", "session_id": "sess-1"},
            transport,
            1,
            "c1",
        )
        assert result["status"] == "completed"
        assert result["id"] == "t1"

    @pytest.mark.anyio
    async def test_raises_for_missing_task_id(self, runtime, transport):
        with pytest.raises(ValueError, match="task_id is required"):
            await handle_todo_update(
                runtime, {"session_id": "sess-1"}, transport, 1, "c1"
            )

    @pytest.mark.anyio
    async def test_raises_for_missing_session_id(self, runtime, transport):
        runtime.current_session_id = None
        with pytest.raises(ValueError, match="session_id is required"):
            await handle_todo_update(runtime, {"task_id": "t1"}, transport, 1, "c1")

    @pytest.mark.anyio
    async def test_raises_for_nonexistent_task(self, runtime, transport):
        runtime.todo_manager.update_task.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await handle_todo_update(
                runtime,
                {"task_id": "no-such", "session_id": "sess-1"},
                transport,
                1,
                "c1",
            )

    @pytest.mark.anyio
    async def test_updates_content(self, runtime, transport):
        runtime.todo_manager.update_task.return_value = _make_task(
            "t1",
            content="new content",
        )
        result = await handle_todo_update(
            runtime,
            {
                "task_id": "t1",
                "content": "new content",
                "session_id": "sess-1",
            },
            transport,
            1,
            "c1",
        )
        assert result["content"] == "new content"
