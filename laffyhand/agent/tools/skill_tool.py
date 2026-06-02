from pathlib import Path
from typing import Any

from loguru import logger

from laffyhand.agent.skill.models import SkillNotFoundError
from laffyhand.agent.skill.registry import SkillRegistry
from laffyhand.agent.tools.base import BaseTool
from laffyhand.agent.tools.permission import PermissionManager

MAX_SKILL_FILE_SIZE = 1 * 1024 * 1024


class SkillTool(BaseTool):
    name = "skill"
    description = "Load and inject a skill into context."

    def __init__(
        self,
        registry: SkillRegistry,
        permission: PermissionManager | None = None,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._permission = permission or PermissionManager()

    def _input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the skill to load",
                },
            },
            "required": ["name"],
        }

    async def run(self, params: dict[str, Any]) -> str:
        name = params["name"]

        try:
            skill = self._registry.require(name)
        except SkillNotFoundError as e:
            logger.warning(f"Skill not found: {name}")
            return str(e)

        try:
            allowed = await self._permission.ask("skill", [name])
            if not allowed:
                return f"Skill '{name}' denied."
        except RuntimeError as e:
            logger.warning(f"Permission check failed for skill '{name}': {e}")
            return f"Skill '{name}' cannot be loaded: {e}"

        file_size = skill.filepath.stat().st_size
        if file_size > MAX_SKILL_FILE_SIZE:
            logger.warning(
                f"Skill '{name}' file too large ({file_size} bytes), will truncate"
            )
        content = skill.filepath.read_text(encoding="utf-8")
        logger.debug(f"Skill '{name}' file size: {len(content)} bytes")
        if len(content) > MAX_SKILL_FILE_SIZE:
            content = content[:MAX_SKILL_FILE_SIZE] + "\n...[truncated]"

        sibling_files = SkillTool._discover_siblings(skill.base_dir, max_files=10)
        logger.debug(f"Skill '{name}' sibling files: {[f.name for f in sibling_files]}")

        parts: list[str] = [
            f'<skill_content name="{skill.name}">',
            content,
            f"Base directory for this skill: file://{skill.base_dir}",
        ]
        if sibling_files:
            parts.append("<skill_files>")
            for sf in sibling_files:
                parts.append(f"  <file>file://{sf}</file>")
            parts.append("</skill_files>")
        parts.append("</skill_content>")

        logger.info(
            f"Skill '{name}' loaded ({len(content)} chars, {len(sibling_files)} sibling files)"
        )
        return "\n".join(parts)

    @staticmethod
    def _discover_siblings(base_dir: Path, max_files: int = 10) -> list[Path]:
        files: list[Path] = []
        try:
            children = sorted(base_dir.iterdir())
        except PermissionError:
            logger.warning(f"Permission denied listing skill base dir: {base_dir}")
            return files
        for child in children:
            if child.name == "SKILL.md" or child.name.startswith("."):
                continue
            if child.is_file():
                files.append(child)
                if len(files) >= max_files:
                    break
        return files
