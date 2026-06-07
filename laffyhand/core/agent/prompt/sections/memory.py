from laffyhand.core.agent.prompt.context import PromptContext
from laffyhand.core.agent.prompt.section import PromptSection


class MemorySection(PromptSection):
    """Persistent memory entries (``<memory>``).

    Skipped when the memory service is disabled (optional).
    """

    tag = "memory"
    required = False

    async def render(self, context: PromptContext) -> str:
        if context.memory_service is None:
            return ""
        content = (await context.memory_service.read()).strip()
        return f"<{self.tag}>\n{content}\n</{self.tag}>"


class MemoryRulesSection(PromptSection):
    """Memory usage rules (``<memory-rules>``).

    Skipped when the memory service is disabled (optional).
    """

    tag = "memory-rules"
    required = False

    async def render(self, context: PromptContext) -> str:
        if context.memory_service is None:
            return ""
        return context.memory_service.system_prompt.strip()
