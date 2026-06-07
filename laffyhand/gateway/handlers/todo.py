from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from laffyhand.core.runtime import AgentRuntime
    from laffyhand.gateway.transport import Transport


async def handle_todo_list(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str = params.get("session_id", "")
    if not session_id:
        return {"tasks": []}
    status = params.get("status")
    tasks = runtime.todo_manager.get_tasks(session_id, status=status)
    return {
        "tasks": [
            {
                "id": t.id,
                "sessionId": t.session_id,
                "content": t.content,
                "status": t.status,
                "dependsOn": t.depends_on,
                "createdAt": t.created_at.isoformat(),
                "updatedAt": t.updated_at.isoformat(),
                "completedAt": t.completed_at.isoformat() if t.completed_at else None,
                "taskToolId": t.task_tool_id,
                "blockedBy": t.metadata.get("blocked_by", []),
            }
            for t in tasks
        ],
    }


async def handle_todo_update(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str = params.get("session_id", "")
    if not session_id:
        raise ValueError("session_id is required")
    task_id: str = params.get("task_id", "")
    if not task_id:
        raise ValueError("task_id is required")

    from laffyhand.core.session.todo import TodoUpdate as TodoUpdateModel

    updates = TodoUpdateModel(
        status=params.get("status"),
        content=params.get("content"),
    )
    item = runtime.todo_manager.update_task(task_id, session_id, updates)
    if item is None:
        raise ValueError(f"Task not found: {task_id}")
    return {
        "id": item.id,
        "sessionId": item.session_id,
        "content": item.content,
        "status": item.status,
        "dependsOn": item.depends_on,
        "createdAt": item.created_at.isoformat(),
        "updatedAt": item.updated_at.isoformat(),
        "completedAt": item.completed_at.isoformat() if item.completed_at else None,
        "taskToolId": item.task_tool_id,
        "blockedBy": item.metadata.get("blocked_by", []),
    }
