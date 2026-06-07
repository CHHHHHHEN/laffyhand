from laffyhand.core._utils import build_env_block
from laffyhand.core.agent.prompt.context import PromptContext
from laffyhand.core.agent.prompt.section import PromptSection


class EnvSection(PromptSection):
    """Workspace environment block (``<env>``)."""

    tag = "env"

    async def render(self, context: PromptContext) -> str:
        return build_env_block(context.workspace)
