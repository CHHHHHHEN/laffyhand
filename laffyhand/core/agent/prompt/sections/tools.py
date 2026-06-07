from laffyhand.core.agent.prompt.context import PromptContext
from laffyhand.core.agent.prompt.section import PromptSection


class ToolsSection(PromptSection):
    """Tool reference list (``<tools>``)."""

    tag = "tools"

    async def render(self, context: PromptContext) -> str:
        return context.tool_registry.build_tool_prompt(
            exclude=context.disabled_tools,
        )
