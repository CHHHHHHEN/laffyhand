from pathlib import Path

from pydantic import BaseModel


class SkillInfo(BaseModel):
    name: str
    description: str | None = None
    base_dir: Path
    filepath: Path


class SkillNotFoundError(LookupError):
    def __init__(self, name: str, available: list[str]) -> None:
        self.skill_name = name
        self.available = available
        avail = ", ".join(available) if available else "(none)"
        super().__init__(f"Skill '{name}' not found. Available skills: {avail}")
