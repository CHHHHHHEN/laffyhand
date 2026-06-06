from __future__ import annotations

import asyncio

import pytest

from laffyhand.core.memory.service import MemoryFormatError, MemoryService
from laffyhand.core.tools.memory import MemoryTool


@pytest.fixture
def memory_path(tmp_path):
    p = tmp_path / "Memory.md"
    p.write_text("# Memory\n")
    return str(p)


@pytest.fixture
def service(memory_path):
    return MemoryService(path=memory_path, max_length=1000)


@pytest.fixture
def tool(service):
    return MemoryTool(service)


class TestMemoryService:
    @pytest.mark.anyio
    async def test_read_empty(self, service):
        content = await service.read()
        assert content == "# Memory\n"

    @pytest.mark.anyio
    async def test_read_missing_file(self):
        svc = MemoryService(path="/nonexistent/memory.md", max_length=1000)
        content = await svc.read()
        assert content == "# Memory\n"

    @pytest.mark.anyio
    async def test_append(self, service):
        ok, msg = await service.append("User prefers concise code.")
        assert ok
        assert "Appended entry 1" in msg
        content = await service.read()
        assert "1. User prefers concise code." in content

    @pytest.mark.anyio
    async def test_append_multiple(self, service):
        await service.append("Entry A")
        await service.append("Entry B")
        await service.append("Entry C")
        content = await service.read()
        assert "1. Entry A" in content
        assert "2. Entry B" in content
        assert "3. Entry C" in content

    @pytest.mark.anyio
    async def test_append_empty_allowed(self, service):
        ok, msg = await service.append("")
        assert ok
        content = await service.read()
        assert "1. " in content

    @pytest.mark.anyio
    async def test_update(self, service):
        await service.append("Old content")
        ok, msg = await service.update(1, "New content")
        assert ok
        assert "Updated entry 1" in msg
        content = await service.read()
        assert "1. New content" in content

    @pytest.mark.anyio
    async def test_update_out_of_range(self, service):
        await service.append("Entry")
        ok, msg = await service.update(999, "Whatever")
        assert not ok
        assert "out of range" in msg

    @pytest.mark.anyio
    async def test_delete(self, service):
        await service.append("Entry A")
        await service.append("Entry B")
        await service.append("Entry C")
        ok, msg = await service.delete(2)
        assert ok
        assert "Deleted entry 2" in msg
        assert "Entry B" in msg
        content = await service.read()
        assert "1. Entry A" in content
        assert "2. Entry C" in content
        assert "Entry B" not in content

    @pytest.mark.anyio
    async def test_delete_out_of_range(self, service):
        ok, msg = await service.delete(1)
        assert not ok
        assert "out of range" in msg

    @pytest.mark.anyio
    async def test_clear(self, service):
        await service.append("Entry A")
        await service.append("Entry B")
        ok, msg = await service.clear()
        assert ok
        assert "Memory cleared" in msg
        content = await service.read()
        assert content.strip() == "# Memory"

    @pytest.mark.anyio
    async def test_max_length_enforced_on_append(self, tmp_path):
        svc = MemoryService(path=str(tmp_path / "short.md"), max_length=20)
        ok, msg = await svc.append("This is a very long entry that should exceed the limit")
        assert not ok
        assert "max length" in msg

    @pytest.mark.anyio
    async def test_max_length_enforced_on_update(self, service):
        await service.append("short")
        ok, msg = await service.update(1, "x" * 2000)
        assert not ok
        assert "max length" in msg

    def test_parse_rejects_non_numbered_content(self, service):
        content = "# Memory\n\nSome freeform text\n"
        with pytest.raises(MemoryFormatError, match="freeform"):
            service._parse_entries(content)

    @pytest.mark.anyio
    async def test_append_rejects_non_numbered_existing_content(self, service):
        service._path.write_text("# Memory\n\nSome junk\n", encoding="utf-8")
        ok, msg = await service.append("New entry")
        assert not ok
        assert "not a numbered entry" in msg

    @pytest.mark.anyio
    async def test_update_rejects_non_numbered_content(self, service):
        service._path.write_text("# Memory\n\njunk\n", encoding="utf-8")
        ok, msg = await service.update(1, "fixed")
        assert not ok
        assert "not a numbered entry" in msg

    @pytest.mark.anyio
    async def test_delete_rejects_non_numbered_content(self, service):
        service._path.write_text("# Memory\n\njunk\n", encoding="utf-8")
        ok, msg = await service.delete(1)
        assert not ok
        assert "not a numbered entry" in msg

    @pytest.mark.anyio
    async def test_concurrent_append(self, service):
        async def do_append(n: int) -> None:
            await service.append(f"Entry {n}")

        await asyncio.gather(*[do_append(i) for i in range(20)])

        content = await service.read()
        for i in range(20):
            assert f"Entry {i}" in content, f"Entry {i} not found"
        entries = service._parse_entries(content)
        assert len(entries) == 20

    def test_system_prompt_property(self, service):
        prompt = service.system_prompt
        assert "## Memory System" in prompt
        assert "What to Remember" in prompt
        assert "What NOT to Remember" in prompt
        assert "When Capacity Is Limited" in prompt

    def test_format_entries_empty(self, service):
        result = service._format_entries([])
        assert result == "# Memory\n"

    def test_format_entries_nonempty(self, service):
        result = service._format_entries(["Entry 1", "Entry 2"])
        assert "# Memory" in result
        assert "1. Entry 1" in result
        assert "2. Entry 2" in result

    def test_parse_basic(self, service):
        entries = service._parse_entries("# Memory\n1. A\n2. B\n")
        assert entries == ["A", "B"]


class TestMemoryTool:
    @pytest.mark.anyio
    async def test_read_empty(self, tool):
        result = await tool.run({"operation": "read"})
        assert "Memory is empty" in result

    @pytest.mark.anyio
    async def test_append_and_read(self, tool):
        await tool.run({"operation": "append", "entry": "Important fact"})
        result = await tool.run({"operation": "read"})
        assert "Important fact" in result

    @pytest.mark.anyio
    async def test_append_requires_entry(self, tool):
        result = await tool.run({"operation": "append"})
        assert "entry is required" in result

    @pytest.mark.anyio
    async def test_update(self, tool):
        await tool.run({"operation": "append", "entry": "Old fact"})
        result = await tool.run({"operation": "update", "index": 1, "entry": "New fact"})
        assert "Updated entry" in result
        read_result = await tool.run({"operation": "read"})
        assert "New fact" in read_result

    @pytest.mark.anyio
    async def test_update_requires_index(self, tool):
        result = await tool.run({"operation": "update", "entry": "something"})
        assert "index is required" in result

    @pytest.mark.anyio
    async def test_update_requires_entry(self, tool):
        result = await tool.run({"operation": "update", "index": 1})
        assert "entry is required" in result

    @pytest.mark.anyio
    async def test_delete(self, tool):
        await tool.run({"operation": "append", "entry": "Delete me"})
        result = await tool.run({"operation": "delete", "index": 1})
        assert "Deleted" in result
        read_result = await tool.run({"operation": "read"})
        assert "Memory is empty" in read_result

    @pytest.mark.anyio
    async def test_delete_requires_index(self, tool):
        result = await tool.run({"operation": "delete"})
        assert "index is required" in result

    @pytest.mark.anyio
    async def test_clear(self, tool):
        await tool.run({"operation": "append", "entry": "Something"})
        result = await tool.run({"operation": "clear"})
        assert "Memory cleared" in result
        read_result = await tool.run({"operation": "read"})
        assert "Memory is empty" in read_result

    @pytest.mark.anyio
    async def test_unknown_operation(self, tool):
        result = await tool.run({"operation": "unknown"})
        assert "unknown operation" in result
