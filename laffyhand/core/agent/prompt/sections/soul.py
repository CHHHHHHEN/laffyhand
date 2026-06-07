from laffyhand.core.agent.prompt.context import PromptContext
from laffyhand.core.agent.prompt.section import PromptSection


class SoulSection(PromptSection):
    """The agent's core identity and instructions (``<soul>``).

    Takes the already-resolved base prompt text.
    """

    tag = "soul"

    def __init__(self, content: str) -> None:
        self._content = content

    async def render(self, context: PromptContext) -> str:
        return f"<{self.tag}>\n{self._content.strip()}\n</{self.tag}>"
