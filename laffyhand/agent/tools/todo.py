from __future__ import annotations

from typing import TYPE_CHECKING, Any

from laffyhand.agent.session.todo import TodoCreate, TodoUpdate
from laffyhand.agent.tools.base import BaseTool

if TYPE_CHECKING:
    from laffyhand.agent.session.todo import TodoManager


class TodoTool(BaseTool):
    name = "todowrite"
    description = "Manage a session-level task list with DAG dependency tracking. "
    "Task IDs: auto-generated (YYYYMMDD_HHMMSS_xxxxxxxx) or custom short IDs. "

    def __init__(self, todo_manager: TodoManager) -> None:
        super().__init__()
        self._todo_manager = todo_manager

    def _input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["read", "add", "update", "delete", "plan", "cleanup"],
                    "description": "Operation to perform. "
                    "read: list tasks. "
                    "add: create one task. "
                    "update: change task status/priority/content/depends. "
                    "delete: remove task(s) by id(s). "
                    "plan: batch create with dependencies. "
                    "cleanup: remove completed/cancelled tasks.",
                },
                "id": {
                    "type": "string",
                    "description": "Single task ID (required for update/delete single task)",
                },
                "ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Multiple task IDs (for batch delete/update)",
                },
                "content": {
                    "type": "string",
                    "description": "Task description (required for add)",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "cancelled"],
                    "description": "New status (for update)",
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Priority (default: medium)",
                },
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs this task depends on (for add/plan)",
                },
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Optional custom short ID for plan references",
                            },
                            "content": {"type": "string"},
                            "priority": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Task IDs this task depends on",
                            },
                        },
                        "required": ["content"],
                    },
                    "description": "List of tasks for plan operation",
                },
            },
            "required": ["operation"],
        }

    async def run(self, params: dict[str, Any]) -> str:
        op = params["operation"]
        session_id = params.get("session_id") or ""
        if not session_id:
            return "Error: session_id is required (runtime did not inject it)"

        if op == "read":
            status = params.get("status")
            tasks = self._todo_manager.get_tasks(session_id, status=status)
            if not tasks:
                return "No tasks."
            lines = []
            for t in tasks:
                blocked = t.metadata.get("blocked_by", [])
                blocked_str = f" [blocked by: {', '.join(blocked)}]" if blocked else ""
                lines.append(
                    f"{t.id} [{t.status}] {t.priority}: {t.content}{blocked_str}"
                )
            return "\n".join(lines)

        if op == "plan":
            raw_tasks: list[dict[str, Any]] = params.get("tasks", [])
            if not raw_tasks:
                return "Error: tasks list is required for plan"
            creates = [
                TodoCreate(
                    id=t.get("id"),
                    content=t.get("content", ""),
                    priority=t.get("priority", "medium"),
                    depends_on=t.get("depends_on", []),
                )
                for t in raw_tasks
            ]
            try:
                results = self._todo_manager.add_tasks(session_id, creates)
            except ValueError as e:
                return f"Error: {e}"
            summary = ", ".join(f"#{t.id} [{t.status}] {t.content}" for t in results)
            return f"Planned {len(results)} task(s): {summary}"

        if op == "add":
            content = params.get("content")
            if not content:
                return "Error: content is required for add"
            try:
                item = self._todo_manager.add_task(
                    session_id,
                    content=content,
                    priority=params.get("priority", "medium"),
                    depends_on=params.get("depends_on"),
                )
            except ValueError as e:
                return f"Error: {e}"
            return f"Added todo #{item.id}: {item.content}"

        if op == "update":
            task_ids: list[str] | None = params.get("ids")
            task_id: str | None = params.get("id")
            if not task_ids and not task_id:
                return "Error: id or ids is required for update"
            status = params.get("status")
            priority = params.get("priority")
            content = params.get("content")
            depends_on = params.get("depends_on")
            updates = TodoUpdate(
                content=content,
                status=status,
                priority=priority,
                depends_on=depends_on,
            )
            if task_ids:
                updated_list = self._todo_manager.update_tasks(
                    task_ids, session_id, updates
                )
                if not updated_list:
                    return "Error: no tasks found to update"
                return f"Updated {len(updated_list)} task(s): " + ", ".join(
                    f"#{t.id} → status={t.status}, priority={t.priority}"
                    for t in updated_list
                )
            else:
                assert task_id is not None
                updated = self._todo_manager.update_task(task_id, session_id, updates)
                if updated is None:
                    return f"Error: task #{task_id} not found"
                return f"Updated todo #{task_id} → status={updated.status}, priority={updated.priority}"

        if op == "delete":
            task_ids = params.get("ids")
            task_id = params.get("id")
            if not task_ids and not task_id:
                return "Error: id or ids is required for delete"
            if task_ids:
                count = self._todo_manager.delete_tasks(task_ids)
                if count == 0:
                    return "Error: no tasks found to delete"
                return f"Deleted {count} task(s)"
            else:
                assert task_id is not None
                if self._todo_manager.delete_task(task_id):
                    return f"Deleted todo #{task_id}"
                return f"Error: task #{task_id} not found"

        if op == "cleanup":
            count = self._todo_manager.cleanup_tasks(session_id)
            if count == 0:
                return "No completed or cancelled tasks to clean up."
            return f"Cleaned up {count} completed/cancelled task(s)."

        return f"Unknown operation: {op}"
