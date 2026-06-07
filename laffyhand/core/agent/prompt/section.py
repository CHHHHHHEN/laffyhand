from __future__ import annotations

from abc import ABC, abstractmethod

from laffyhand.core.agent.prompt.context import PromptContext


class PromptSection(ABC):
    """A modular section of the system prompt.

    Each subclass produces one XML-tagged block.
    Subclasses set ``tag`` and implement ``render()``.
    The ``render()`` method is responsible for returning the full
    XML block (including its own tags), because some sections
    delegate to existing renderers that already produce wrapped output.
    """

    tag: str = ""
    required: bool = True

    @abstractmethod
    async def render(self, context: PromptContext) -> str:
        """Return the full XML block (including outer tags).

        Return ``""`` when the section has no content to emit
        (e.g. optional section with nothing to show).
        """
        ...

    async def build(self, context: PromptContext) -> str:
        """Render the section.

        Returns empty string when the section is optional and renders empty.
        """
        content = await self.render(context)
        if not content and not self.required:
            return ""
        return content
