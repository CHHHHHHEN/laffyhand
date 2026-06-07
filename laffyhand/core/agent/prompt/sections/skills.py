from laffyhand.core.agent.prompt.context import PromptContext
from laffyhand.core.agent.prompt.section import PromptSection


class SkillsSection(PromptSection):
    """Loaded skills summary (``<skills>``).

    Skipped automatically when no skills are loaded (optional).
    """

    tag = "skills"
    required = False

    async def render(self, context: PromptContext) -> str:
        if not context.skill_registry.all():
            return ""
        return context.skill_registry.build_skills_summary()
