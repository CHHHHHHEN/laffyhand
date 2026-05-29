import json
import tempfile
import uuid
from pathlib import Path
from typing import Any
from datetime import datetime

from loguru import logger
from laffyhand.agent.tools.base import BaseTool


class TodoTool(BaseTool):
    name = "todo"
    description = "Manage a task list with priorities and status tracking."

    def _input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "add", "update", "delete"],
                    "description": "Action to perform on todos",
                },
                "content": {
                    "type": "string",
                    "description": "Task description (required for add)",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "cancelled"],
                    "description": "Status to set (required for update)",
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Priority (default: medium)",
                },
                "id": {
                    "type": "string",
                    "description": "Todo ID (required for update/delete)",
                },
            },
            "required": ["action"],
        }

    def __init__(self, todo_path: str | None = None) -> None:
        super().__init__()
        self._todo_path = todo_path or ".todos.json"

    def _load(self) -> list[dict]:
        path = Path(self._todo_path)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return []
        return []

    def _save(self, todos: list[dict]) -> None:
        path = Path(self._todo_path)
        data = json.dumps(todos, indent=2, ensure_ascii=False)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(data)
            Path(tmp).replace(path)
        except:
            Path(tmp).unlink(missing_ok=True)
            raise

    def run(self, params: dict[str, Any]) -> str:
        action = params["action"]
        todos = self._load()

        if action == "read":
            if not todos:
                return "No todos."
            lines = [
                f"{t['id']} [{t['status']}] {t.get('priority', 'medium')}: {t['content']}"
                for t in todos
            ]
            return "\n".join(lines)

        if action == "add":
            content = params.get("content")
            if not content:
                logger.warning("Todo add: content is required")
                return "content is required for add"
            todo_id = uuid.uuid4().hex[:8]
            todos.append({
                "id": todo_id,
                "content": content,
                "status": "pending",
                "priority": params.get("priority", "medium"),
                "created": datetime.now().isoformat(),
            })
            self._save(todos)
            logger.info(f"Added todo #{todo_id}")
            return f"Added todo #{todo_id}: {content}"

        if action == "update":
            uid = params.get("id")
            ust = params.get("status")
            if not uid or not ust:
                logger.warning("Todo update: id or status missing")
                return "id and status are required for update"
            for t in todos:
                if t["id"] == uid:
                    t["status"] = ust
                    self._save(todos)
                    logger.info(f"Updated todo #{uid} → {ust}")
                    return f"Updated todo #{uid} → {ust}"
            logger.warning(f"Todo #{uid} not found for update")
            return f"Todo #{uid} not found"

        if action == "delete":
            did = params.get("id")
            if not did:
                logger.warning("Todo delete: id is required")
                return "id is required for delete"
            new_todos = [t for t in todos if t["id"] != did]
            if len(new_todos) == len(todos):
                logger.warning(f"Todo #{did} not found for delete")
                return f"Todo #{did} not found"
            self._save(new_todos)
            logger.info(f"Deleted todo #{did}")
            return f"Deleted todo #{did}"

        logger.warning(f"Unknown todo action: {action}")
        return f"Unknown action: {action}"
