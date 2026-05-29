import unittest
import tempfile
import json
from pathlib import Path
from laffyhand.agent.tools.todo import TodoTool


class TestTodoTool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.todo_path = str(Path(self.tmpdir.name) / "todos.json")
        self.tool = TodoTool(todo_path=self.todo_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_read_empty(self):
        result = self.tool.run({"action": "read"})
        self.assertIn("No todos", result)

    def test_add_and_read(self):
        self.tool.run({"action": "add", "content": "test task", "priority": "high"})
        result = self.tool.run({"action": "read"})
        self.assertIn("test task", result)
        self.assertIn("high", result)

    def test_add_requires_content(self):
        result = self.tool.run({"action": "add"})
        self.assertIn("content is required", result)

    def test_update_status(self):
        self.tool.run({"action": "add", "content": "task"})
        items = json.loads(Path(self.todo_path).read_text())
        todo_id = items[0]["id"]
        self.tool.run({"action": "update", "id": todo_id, "status": "completed"})
        items = json.loads(Path(self.todo_path).read_text())
        self.assertEqual(items[0]["status"], "completed")

    def test_update_requires_id_and_status(self):
        result = self.tool.run({"action": "update", "id": "1"})
        self.assertIn("id", result.lower() or "status" in result.lower())

    def test_delete(self):
        self.tool.run({"action": "add", "content": "task"})
        items = json.loads(Path(self.todo_path).read_text())
        todo_id = items[0]["id"]
        self.tool.run({"action": "delete", "id": todo_id})
        result = self.tool.run({"action": "read"})
        self.assertIn("No todos", result)

    def test_delete_unknown(self):
        result = self.tool.run({"action": "delete", "id": "999"})
        self.assertIn("not found", result.lower())

    def test_unknown_action(self):
        result = self.tool.run({"action": "unknown"})
        self.assertIn("Unknown action", result)
