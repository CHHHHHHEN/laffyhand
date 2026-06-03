from laffyhand.agent.llm.specs.models import Message
from laffyhand.agent.prune import prune
from laffyhand.agent.schemas import AgentState, CompactionConfig


def build_llm_context(
    agent_state: AgentState,
    compaction_config: CompactionConfig,
) -> list[Message]:
    if compaction_config.prune:
        return prune(agent_state.messages)
    return agent_state.messages
