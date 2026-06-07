from laffyhand.core.agent.prompt.context import PromptContext
from laffyhand.core.agent.prompt.section import PromptSection


class PreferencesSection(PromptSection):
    """AGENTS.md preference rules (``<preference>``).

    Skipped when no preference file is found (optional).
    """

    tag = "preference"
    required = False

    async def render(self, context: PromptContext) -> str:
        if context.preference_service is None:
            return ""
        return await context.preference_service.load_preferences()
