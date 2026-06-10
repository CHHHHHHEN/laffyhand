from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from loguru import logger
from pydantic import BaseModel


AgentMode = Literal["primary", "subagent", "all"]

_PROMPTS_DIR = Path(__file__).parent / "prompts"


class AgentInfo(BaseModel):
    name: str
    system_prompt: str
    description: str = ""
    mode: AgentMode = "subagent"
    model: str | None = None
    permission: dict[str, Any] = {}
    max_steps: int = 50
    temperature: float | None = None
    top_p: float | None = None
    hidden: bool = False
    options: dict[str, Any] = {}


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = {}
        if _PROMPTS_DIR.is_dir():
            self.discover([str(_PROMPTS_DIR)])

    def register(self, info: AgentInfo) -> None:
        self._agents[info.name] = info
        logger.debug(f"Agent registered: {info.name} ({info.mode})")

    def get(self, name: str) -> AgentInfo | None:
        return self._agents.get(name)

    def list_by_mode(self, mode: AgentMode) -> list[AgentInfo]:
        return [a for a in self._agents.values() if a.mode == mode or a.mode == "all"]

    def list_subagents(self) -> list[AgentInfo]:
        return self.list_by_mode("subagent")

    def list_visible(self) -> list[AgentInfo]:
        return [a for a in self._agents.values() if not a.hidden]

    def discover(self, dirs: list[str | Path]) -> None:
        for d in dirs:
            path = Path(d)
            if not path.is_dir():
                continue
            for f in sorted(path.iterdir()):
                if f.suffix == ".md" and f.stem not in ("README", "template_agent"):
                    info = _load_agent_file(f)
                    if info is not None:
                        self.register(info)


def _load_agent_file(path: Path) -> AgentInfo | None:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read agent file {path}: {e}")
        return None

    if not text.startswith("---"):
        return None

    parts = text.split("---", 2)
    if len(parts) < 3:
        logger.warning(f"Agent file {path} missing YAML front-matter closing ---")
        return None

    raw = parts[1].strip()
    body = parts[2].strip()

    try:
        meta = yaml.safe_load(raw)
    except Exception as e:
        logger.warning(f"Failed to parse YAML front-matter in {path}: {e}")
        return None

    if not isinstance(meta, dict):
        return None

    name = meta.get("name") or path.stem
    return AgentInfo(
        name=name,
        system_prompt=body or meta.get("system_prompt", ""),
        description=meta.get("description", ""),
        mode=meta.get("mode", "subagent"),
        model=meta.get("model"),
        permission=meta.get("permission", {}),
        max_steps=meta.get("max_steps", 50),
        temperature=meta.get("temperature"),
        top_p=meta.get("top_p"),
        hidden=meta.get("hidden", False),
        options=meta.get("options", {}),
    )


def get_builtin(name: str) -> AgentInfo | None:
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        return None
    return _load_agent_file(path)
