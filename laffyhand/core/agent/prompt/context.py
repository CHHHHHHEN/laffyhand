from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PromptContext:
    """Dynamic context passed to all sections during rendering.

    Carries runtime references that sections need to produce their content.
    """

    workspace: str | None = None
    disabled_tools: set[str] = field(default_factory=set)
    tool_registry: Any = None
    skill_registry: Any = None
    preference_service: Any = None
    memory_service: Any = None
