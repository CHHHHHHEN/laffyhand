from pathlib import Path

from loguru import logger

from laffyhand.agent.skill.models import SkillInfo
from laffyhand.agent.skill.parser import parse_skill_md


def discover_skills(dirs: list[str | Path]) -> dict[str, SkillInfo]:
    """Scan directories for SKILL.md files and return a mapping of name → SkillInfo."""
    skills: dict[str, SkillInfo] = {}
    seen: set[Path] = set()

    for d in dirs:
        root = Path(d)
        if not root.is_dir():
            logger.debug(f"Skill discovery dir {root} does not exist, skipping")
            continue
        for skill_file in sorted(root.rglob("SKILL.md")):
            if skill_file in seen:
                continue
            seen.add(skill_file)
            info = parse_skill_md(skill_file)
            if info is None:
                continue
            if info.name in skills:
                logger.warning(f"Duplicate skill '{info.name}' from {info.filepath}, overwriting previous")
            skills[info.name] = info
            logger.debug(f"Discovered skill '{info.name}' at {info.filepath}")

    logger.info(f"Discovered {len(skills)} skill(s): {list(skills.keys())}")
    return skills
