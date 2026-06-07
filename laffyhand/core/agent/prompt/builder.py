from __future__ import annotations

from laffyhand.core.agent.prompt.context import PromptContext
from laffyhand.core.agent.prompt.section import PromptSection


class PromptBuilder:
    """Declarative system-prompt assembler.

    Usage::

        builder = PromptBuilder(context)
        builder.add(SoulSection(...))
        builder.add(EnvSection())
        ...
        prompt = await builder.build()
    """

    def __init__(self, context: PromptContext) -> None:
        self._context = context
        self._sections: list[PromptSection] = []

    def add(self, section: PromptSection) -> PromptBuilder:
        """Append one section to the layout."""
        self._sections.append(section)
        return self

    async def build(self) -> str:
        """Render all sections in order and join with newlines."""
        parts: list[str] = []
        for section in self._sections:
            rendered = await section.build(self._context)
            if rendered:
                parts.append(rendered)
        return "\n".join(parts)
