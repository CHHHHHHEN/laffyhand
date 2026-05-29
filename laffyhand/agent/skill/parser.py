from pathlib import Path

from loguru import logger

from laffyhand.agent.skill.models import SkillInfo


def _parse_frontmatter(text: str) -> dict | None:
    """Extract YAML-like frontmatter between --- delimiters."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None
    raw = "\n".join(lines[1:end_idx])
    result: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip("\"'")
    return result


def parse_skill_md(filepath: Path) -> SkillInfo | None:
    """Parse a SKILL.md file and return SkillInfo, or None on failure."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read skill file {filepath}: {e}")
        return None

    frontmatter = _parse_frontmatter(text)
    if frontmatter is None:
        logger.warning(f"Skill file {filepath} has no frontmatter, skipping")
        return None

    name = frontmatter.get("name")
    if not name:
        logger.warning(f"Skill file {filepath} has no 'name' field, skipping")
        return None

    description = frontmatter.get("description")
    return SkillInfo(
        name=name,
        description=description,
        base_dir=filepath.parent,
        filepath=filepath,
    )
