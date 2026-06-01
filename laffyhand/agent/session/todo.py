from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional, cast

from loguru import logger
from typing import TYPE_CHECKING
from laffyhand.agent.session.models import (
    TodoCreate,
    TodoItem,
    TodoUpdate,
    TodoPriority,
    TodoStatus,
    _utcnow,
    _ts,
    _from_ts,
)

if TYPE_CHECKING:
    from laffyhand.agent.session.manager import SessionManager


def _serialize_json(val: list[Any] | dict[str, Any]) -> str:
    return json.dumps(val, default=str)


def _deserialize_str_list(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        return cast(list[str], json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        return []


def _deserialize_metadata(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return cast(dict[str, Any], json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        return {}


class TodoManager:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @classmethod
    def from_session_manager(cls, sm: SessionManager) -> TodoManager:
        return cls(sm.connection)

    # ── CRUD ─────────────────────────────────────────────────

    def get_task(self, task_id: str) -> Optional[TodoItem]:
        row = self._conn.execute(
            "SELECT * FROM todo WHERE id = ?",
            (task_id,),
        ).fetchone()
        return self._row_to_todo(row) if row else None

    def get_tasks(
        self, session_id: str, status: Optional[str] = None
    ) -> list[TodoItem]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM todo WHERE session_id = ? AND status = ? ORDER BY created_at",
                (session_id, status),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM todo WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            ).fetchall()
        tasks = [self._row_to_todo(r) for r in rows]
        self._compute_blocked(tasks)
        return tasks

    def add_task(
        self,
        session_id: str,
        content: str,
        priority: TodoPriority = "medium",
        depends_on: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> TodoItem:
        item = TodoItem(
            session_id=session_id,
            content=content,
            priority=priority,
            depends_on=depends_on or [],
            metadata=metadata or {},
        )
        existing = self.get_tasks(session_id)
        if depends_on:
            self._validate_depends(depends_on, existing, task_id=item.id)
        now = _utcnow()
        self._conn.execute(
            """INSERT INTO todo
               (id, session_id, content, status, priority, depends_on,
                created_at, updated_at, completed_at, task_tool_id, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.id,
                item.session_id,
                item.content,
                item.status,
                item.priority,
                _serialize_json(item.depends_on),
                _ts(now),
                _ts(now),
                None,
                None,
                _serialize_json(item.metadata),
            ),
        )
        self._conn.commit()
        return item

    def add_tasks(
        self,
        session_id: str,
        tasks: list[TodoCreate],
    ) -> list[TodoItem]:
        existing = self.get_tasks(session_id)
        existing_ids = {t.id for t in existing}
        ids: list[str] = []
        for t in tasks:
            item = TodoItem(
                id=t.id or "",
                session_id=session_id,
                content=t.content,
                priority=t.priority,
                depends_on=t.depends_on,
            )
            if t.depends_on:
                resolved = [d for d in t.depends_on if d in ids or d in existing_ids]
                unresolved = [
                    d for d in t.depends_on if d not in ids and d not in existing_ids
                ]
                if unresolved:
                    logger.warning(
                        f"add_tasks: dependencies {unresolved} not resolvable in batch for task {t.content[:50]}"
                    )
                self._validate_depends(resolved, existing, task_id=item.id)
                item.depends_on = resolved
            else:
                item.depends_on = []
            now = _utcnow()
            self._conn.execute(
                """INSERT INTO todo
                   (id, session_id, content, status, priority, depends_on,
                    created_at, updated_at, completed_at, task_tool_id, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.id,
                    item.session_id,
                    item.content,
                    item.status,
                    item.priority,
                    _serialize_json(item.depends_on),
                    _ts(now),
                    _ts(now),
                    None,
                    None,
                    _serialize_json(item.metadata),
                ),
            )
            ids.append(item.id)
            existing = self.get_tasks(session_id)
            existing_ids = {t.id for t in existing}
        self._conn.commit()
        return self.get_tasks(session_id)

    def update_task(
        self,
        task_id: str,
        session_id: str,
        updates: TodoUpdate,
    ) -> Optional[TodoItem]:
        item = self.get_task(task_id)
        if item is None:
            return None

        if updates.content is not None:
            item.content = updates.content
        if updates.priority is not None:
            item.priority = updates.priority
        if updates.depends_on is not None:
            existing = self.get_tasks(session_id)
            self._validate_depends(updates.depends_on, existing, task_id=item.id)
            item.depends_on = updates.depends_on
        if "task_tool_id" in updates.model_fields_set:
            item.task_tool_id = updates.task_tool_id
        if updates.metadata is not None:
            item.metadata = updates.metadata
        old_status = item.status
        if updates.status is not None:
            item.status = updates.status
            if updates.status == "completed" and old_status != "completed":
                item.completed_at = _utcnow()
            elif updates.status != "completed":
                item.completed_at = None

        item.updated_at = _utcnow()
        self._conn.execute(
            """UPDATE todo SET
                content=?, status=?, priority=?, depends_on=?,
                updated_at=?, completed_at=?, task_tool_id=?, metadata=?
               WHERE id=?""",
            (
                item.content,
                item.status,
                item.priority,
                _serialize_json(item.depends_on),
                _ts(item.updated_at),
                _ts(item.completed_at),
                item.task_tool_id,
                _serialize_json(item.metadata),
                item.id,
            ),
        )
        self._conn.commit()

        if updates.status == "completed":
            self.resolve_blocked(task_id, session_id)
        elif (
            old_status == "completed"
            and updates.status is not None
            and updates.status != "completed"
        ):
            all_tasks = self.get_tasks(session_id)
            now = _utcnow()
            for t in all_tasks:
                self._conn.execute(
                    "UPDATE todo SET status=?, updated_at=?, metadata=? WHERE id=?",
                    (t.status, _ts(now), _serialize_json(t.metadata), t.id),
                )
            self._conn.commit()

        return item

    def delete_task(self, task_id: str) -> bool:
        item = self.get_task(task_id)
        if item is None:
            return False
        # Remove this task from all dependents' depends_on lists
        dependents = self._conn.execute(
            "SELECT id, depends_on FROM todo WHERE depends_on LIKE ?",
            (f"%{task_id}%",),
        ).fetchall()
        for dep in dependents:
            deps = _deserialize_str_list(dep["depends_on"])
            if task_id in deps:
                deps.remove(task_id)
                self._conn.execute(
                    "UPDATE todo SET depends_on = ? WHERE id = ?",
                    (_serialize_json(deps), dep["id"]),
                )
        self._conn.execute("DELETE FROM todo WHERE id = ?", (task_id,))
        self._conn.commit()
        return True

    def delete_session_tasks(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM todo WHERE session_id = ?", (session_id,))
        self._conn.commit()

    # ── DAG ───────────────────────────────────────────────────

    def _compute_blocked(self, tasks: list[TodoItem]) -> None:
        """Populate blocked_by on each task based on depends_on + dependency status."""
        task_map = {t.id: t for t in tasks}
        for t in tasks:
            t.metadata.pop("blocked_by", None)
        for t in tasks:
            blocked_by = [
                dep_id
                for dep_id in t.depends_on
                if dep_id in task_map and task_map[dep_id].status != "completed"
            ]
            if blocked_by:
                t.metadata["blocked_by"] = blocked_by
                if t.status not in ("completed", "cancelled"):
                    t.status = "blocked"

    def _validate_depends(
        self,
        depends_on: list[str],
        existing: list[TodoItem],
        task_id: str | None = None,
    ) -> None:
        """Validate dependencies: all must exist and no cycles.

        For update_task, task_id is the task being modified; verifies
        that the new depends_on don't create a cycle back to task_id.
        """
        existing_ids = {t.id for t in existing}
        for dep_id in depends_on:
            if dep_id not in existing_ids:
                raise ValueError(f"Dependency '{dep_id}' does not exist")
        if task_id and task_id in depends_on:
            raise ValueError("A task cannot depend on itself")
        if task_id:
            for dep_id in depends_on:
                if self._can_reach(dep_id, task_id):
                    raise ValueError("Adding these dependencies would create a cycle")

    def _can_reach(self, start: str, target: str) -> bool:
        """DFS: follow depends_on edges from start; return True if target is reached."""
        visited: set[str] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node == target:
                return True
            if node in visited:
                continue
            visited.add(node)
            row = self._conn.execute(
                "SELECT depends_on FROM todo WHERE id = ?",
                (node,),
            ).fetchone()
            if row:
                deps = _deserialize_str_list(row["depends_on"])
                stack.extend(d for d in deps if d not in visited)
        return False

    def resolve_blocked(self, task_id: str, session_id: str) -> None:
        """After task completes, re-evaluate blocked status for dependents."""
        tasks = self.get_tasks(session_id)
        for t in tasks:
            if task_id in t.depends_on and t.status == "blocked":
                blocked_by = t.metadata.get("blocked_by", [])
                if task_id in blocked_by:
                    remaining = [d for d in blocked_by if d != task_id]
                    if remaining:
                        t.metadata["blocked_by"] = remaining
                    else:
                        t.metadata.pop("blocked_by", None)
                        t.status = "pending"
                        t.updated_at = _utcnow()
                        self._conn.execute(
                            """UPDATE todo SET status=?, updated_at=?, metadata=?
                               WHERE id=?""",
                            (
                                t.status,
                                _ts(t.updated_at),
                                _serialize_json(t.metadata),
                                t.id,
                            ),
                        )
        self._conn.commit()

    # ── TaskTool integration ──────────────────────────────────

    def link_task_tool(self, task_id: str, tool_call_id: str) -> Optional[TodoItem]:
        item = self.get_task(task_id)
        if item is None:
            return None
        return self.update_task(
            task_id,
            item.session_id,
            TodoUpdate(task_tool_id=tool_call_id, status="in_progress"),
        )

    def on_subagent_complete(
        self, tool_call_id: str, success: bool
    ) -> Optional[TodoItem]:
        row = self._conn.execute(
            "SELECT * FROM todo WHERE task_tool_id = ?",
            (tool_call_id,),
        ).fetchone()
        if row is None:
            return None
        item = self._row_to_todo(row)
        new_status: TodoStatus = "completed" if success else "pending"
        return self.update_task(
            item.id,
            item.session_id,
            TodoUpdate(status=new_status, task_tool_id=None),
        )

    # ── Internal ──────────────────────────────────────────────

    @staticmethod
    def _row_to_todo(row: sqlite3.Row) -> TodoItem:
        return TodoItem(
            id=row["id"],
            session_id=row["session_id"],
            content=row["content"],
            status=row["status"],
            priority=row["priority"],
            depends_on=_deserialize_str_list(row["depends_on"]),
            created_at=_from_ts(row["created_at"]) or _utcnow(),
            updated_at=_from_ts(row["updated_at"]) or _utcnow(),
            completed_at=_from_ts(row["completed_at"]) if row["completed_at"] else None,
            task_tool_id=row["task_tool_id"],
            metadata=_deserialize_metadata(row["metadata"]),
        )
