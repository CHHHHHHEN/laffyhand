from pathlib import Path

from laffyhand.core.skill.models import SkillInfo, SkillNotFoundError
from laffyhand.core.skill.discovery import discover_skills


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillInfo] = {}

    def clear(self) -> None:
        self._skills.clear()

    def discover(self, dirs: list[str | Path]) -> None:
        self._skills.update(discover_skills(dirs))

    def get(self, name: str) -> SkillInfo | None:
        return self._skills.get(name)

    def require(self, name: str) -> SkillInfo:
        skill = self._skills.get(name)
        if skill is None:
            raise SkillNotFoundError(name, list(self._skills.keys()))
        return skill

    def all(self) -> list[SkillInfo]:
        return list(self._skills.values())

    def build_skills_summary(self) -> str:
        if not self._skills:
            return ""
        lines = ["<skills>"]
        for info in sorted(self._skills.values(), key=lambda s: s.name):
            desc = info.description or "(no description)"
            lines.append(f"- **{info.name}**: {desc}")
        lines.append("</skills>")
        return "\n".join(lines)
