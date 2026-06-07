"""System-prompt assembly: modular XML-tagged sections.

Public API
----------
- ``assemble_system_prompt()``  — full system prompt for primary agents
- ``assemble_subagent_prompt()`` — minimal prompt for sub-agents
"""

from __future__ import annotations

from typing import Any

from laffyhand.core.agent.prompt.builder import PromptBuilder
from laffyhand.core.agent.prompt.context import PromptContext
from laffyhand.core.agent.prompt.sections import (
    EnvSection,
    MemoryRulesSection,
    MemorySection,
    PreferencesSection,
    SkillsSection,
    SoulSection,
    ToolsSection,
)

__all__ = [
    "assemble_system_prompt",
    "assemble_subagent_prompt",
]


async def assemble_system_prompt(
    base_prompt: str,
    *,
    workspace: str | None = None,
    disabled_tools: set[str] | None = None,
    tool_registry: Any = None,
    skill_registry: Any = None,
    preference_service: Any = None,
    memory_service: Any = None,
) -> str:
    """Build the full system prompt for a primary agent.

    Parameters
    ----------
    base_prompt:
        The agent's identity text (content of ``<soul>``).
    workspace:
        Resolved workspace path.
    disabled_tools:
        Tools to exclude from the prompt.
    tool_registry:
        ``ToolRegistry`` instance.
    skill_registry:
        ``SkillRegistry`` instance.
    preference_service:
        ``PreferenceService`` instance.
    memory_service:
        ``MemoryService`` instance, or ``None`` when disabled.
    """
    context = PromptContext(
        workspace=workspace,
        disabled_tools=disabled_tools or set(),
        tool_registry=tool_registry,
        skill_registry=skill_registry,
        preference_service=preference_service,
        memory_service=memory_service,
    )
    builder = (
        PromptBuilder(context)
        .add(SoulSection(base_prompt))
        .add(EnvSection())
        .add(ToolsSection())
        .add(SkillsSection())
        .add(PreferencesSection())
        .add(MemorySection())
        .add(MemoryRulesSection())
    )
    return await builder.build()


async def assemble_subagent_prompt(
    system_content: str,
    *,
    workspace: str | None = None,
    tool_registry: Any = None,
) -> str:
    """Build the system prompt for a sub-agent.

    Only includes ``<soul>``, ``<env>``, and ``<tools>`` blocks.
    """
    context = PromptContext(
        workspace=workspace,
        tool_registry=tool_registry,
    )
    builder = (
        PromptBuilder(context)
        .add(SoulSection(system_content))
        .add(EnvSection())
        .add(ToolsSection())
    )
    return await builder.build()
