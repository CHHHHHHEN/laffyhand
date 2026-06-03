from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import sqlite3

from laffyhand.agent.session.todo.models import (
    TodoCreate,
    TodoItem,
    TodoUpdate,
    TodoPriority,
    TodoStatus,
)
from laffyhand.agent.session.models import _generate_id, _utcnow

if TYPE_CHECKING:
    from laffyhand.agent.db.repository import TodoRepo
    from laffyhand.agent.session.manager import SessionManager


class TodoManager:
    """Domain logic for todo tasks: DAG validation, blocking resolution, tool integration.

    Delegates all SQL persistence to TodoRepo.
    """

    def __init__(self, repo: TodoRepo, session_manager: SessionManager | None = None) -> None:
        self._repo = repo
        self._session_manager = session_manager

    @classmethod
    def from_session_manager(cls, sm: SessionManager) -> TodoManager:
        from laffyhand.agent.db.repository import TodoRepo
        return cls(TodoRepo(sm.connection), session_manager=sm)

    # ── Helpers ──────────────────────────────────────────────

    def _ensure_session(self, session_id: str) -> None:
        """Ensure the session exists in DB before inserting tasks with FK reference."""
        if self._session_manager is not None:
            self._session_manager.ensure_exists(session_id)

    # ── CRUD (delegates to repo) ─────────────────────────────

    def get_task(self, task_id: str) -> Optional[TodoItem]:
        return self._repo.get(task_id)

    def get_tasks(self, session_id: str, status: Optional[str] = None) -> list[TodoItem]:
        tasks = self._repo.get_by_session(session_id, status=status)
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
        self._ensure_session(session_id)
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
        try:
            self._repo.insert(item)
            self._repo.commit()
        except sqlite3.IntegrityError as e:
            self._repo.rollback()
            err_msg = str(e)
            if "FOREIGN KEY" in err_msg or "session" in err_msg.lower():
                raise ValueError(
                    f"Session '{session_id}' does not exist. "
                    "Cannot add todo task without a valid session."
                ) from e
            raise
        return item

    def add_tasks(
        self,
        session_id: str,
        tasks: list[TodoCreate],
    ) -> list[TodoItem]:
        self._ensure_session(session_id)
        existing = self.get_tasks(session_id)
        existing_ids = {t.id for t in existing}
        ids: list[str] = []
        for t in tasks:
            item = TodoItem(
                id=t.id or _generate_id(),
                session_id=session_id,
                content=t.content,
                priority=t.priority,
                depends_on=t.depends_on,
            )
            if t.depends_on:
                for dep_id in t.depends_on:
                    if dep_id not in ids and dep_id not in existing_ids:
                        raise ValueError(
                            f"Dependency '{dep_id}' for task '{t.content[:50]}' "
                            f"does not exist in this batch or existing tasks"
                        )
                self._validate_depends(t.depends_on, existing, task_id=item.id)
                item.depends_on = t.depends_on
            else:
                item.depends_on = []
            try:
                self._repo.insert(item)
            except sqlite3.IntegrityError as e:
                self._repo.rollback()
                err_msg = str(e)
                if "FOREIGN KEY" in err_msg or "session" in err_msg.lower():
                    raise ValueError(
                        f"Session '{session_id}' does not exist. "
                        "Cannot add todo tasks without a valid session."
                    ) from e
                raise
            ids.append(item.id)
            existing = self._repo.get_by_session(session_id)
            existing_ids = {t.id for t in existing}
        self._repo.commit()
        return self.get_tasks(session_id)

    def update_task(
        self,
        task_id: str,
        session_id: str,
        updates: TodoUpdate,
    ) -> Optional[TodoItem]:
        item = self._repo.get(task_id)
        if item is None:
            return None

        if updates.content is not None:
            item.content = updates.content
        if updates.priority is not None:
            item.priority = updates.priority
        if updates.depends_on is not None:
            existing = self._repo.get_by_session(session_id)
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
        try:
            self._repo.update(item)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise

        if updates.status == "completed":
            self.resolve_blocked(task_id, session_id)
        elif (
            old_status == "completed"
            and updates.status is not None
            and updates.status != "completed"
        ):
            all_tasks = self._repo.get_by_session(session_id)
            now = _utcnow()
            try:
                for t in all_tasks:
                    t.updated_at = now
                    self._repo.update(t)
                self._repo.commit()
            except Exception:
                self._repo.rollback()
                raise

        return item

    def delete_task(self, task_id: str) -> bool:
        item = self._repo.get(task_id)
        if item is None:
            return False
        # Remove this task from all dependents' depends_on lists
        dependents = self._repo.get_dependents(task_id)
        for dep_id, deps in dependents:
            if task_id in deps:
                deps.remove(task_id)
                dep_item = self._repo.get(dep_id)
                if dep_item is not None:
                    dep_item.depends_on = deps
                    dep_item.updated_at = _utcnow()
                    self._repo.update(dep_item)
        self._repo.delete(task_id)
        self._repo.commit()
        return True

    def delete_tasks(self, task_ids: list[str]) -> int:
        """Delete multiple tasks by IDs. Removes references from dependents."""
        count = 0
        for tid in task_ids:
            if self.delete_task(tid):
                count += 1
        return count

    def update_tasks(
        self, task_ids: list[str], session_id: str, updates: TodoUpdate
    ) -> list[TodoItem]:
        """Update multiple tasks with the same updates."""
        results: list[TodoItem] = []
        for tid in task_ids:
            item = self.update_task(tid, session_id, updates)
            if item is not None:
                results.append(item)
        return results

    def cleanup_tasks(
        self, session_id: str, statuses: Optional[list[str]] = None
    ) -> int:
        """Delete tasks matching given statuses (default: completed, cancelled)."""
        if statuses is None:
            statuses = ["completed", "cancelled"]
        tasks = self._repo.get_by_session(session_id)
        ids = [t.id for t in tasks if t.status in statuses]
        return self.delete_tasks(ids)

    def delete_session_tasks(self, session_id: str) -> None:
        try:
            self._repo.delete_by_session(session_id)
            self._repo.commit()
        except Exception:
            self._repo.rollback()
            raise

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
            item = self._repo.get(node)
            if item:
                stack.extend(d for d in item.depends_on if d not in visited)
        return False

    def resolve_blocked(self, task_id: str, session_id: str) -> None:
        """After task completes, re-evaluate blocked status for dependents."""
        tasks = self._repo.get_by_session(session_id)
        changed = False
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
                        self._repo.update(t)
                        changed = True
        if changed:
            self._repo.commit()

    # ── TaskTool integration ──────────────────────────────────

    def link_task_tool(self, task_id: str, tool_call_id: str) -> Optional[TodoItem]:
        item = self._repo.get(task_id)
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
        item = self._repo.get_by_task_tool_id(tool_call_id)
        if item is None:
            return None
        new_status: TodoStatus = "completed" if success else "pending"
        return self.update_task(
            item.id,
            item.session_id,
            TodoUpdate(status=new_status, task_tool_id=None),
        )
