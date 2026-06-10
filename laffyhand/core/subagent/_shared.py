from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from laffyhand.core.models import (
    Compacting,
    ReasoningDelta,
    ReasoningEnd,
    ReasoningStart,
    StepStart,
    SubAgentDelta,
    TextDelta,
    TextEnd,
    TextStart,
    ToolCall,
    ToolError,
    ToolResult,
)
from laffyhand.core.domain.messages import SystemMessage, UserMessage
from laffyhand.core.models import AgentState, SessionID, SessionUsage
from laffyhand.core.agent import assemble_subagent_prompt
from laffyhand.core.tools.permission import SubagentPermissions

if TYPE_CHECKING:
    from laffyhand.core.agent import AgentInfo
    from laffyhand.core.session.manager import SessionManager
    from laffyhand.core.tools.registry import ToolRegistry
    from laffyhand.core.tools.permission import PermissionManager


async def build_subagent_state(
    session_manager: SessionManager,
    parent_session_id: str,
    agent_info: AgentInfo,
    prompt: str,
    parent_permission: PermissionManager,
    tool_registry: ToolRegistry,
) -> tuple[AgentState, ToolRegistry]:
    child_session = session_manager.create_child(
        parent_id=parent_session_id,
        model=agent_info.model or "",
    )

    child_permission = SubagentPermissions.compose(
        parent_permission,
        agent_info.permission,
    )
    child_registry = SubagentPermissions.filter_registry(
        tool_registry,
        child_permission,
    )

    system_content = (
        agent_info.system_prompt
        or "You are a helpful sub-agent. Complete the assigned task."
    )

    system_prompt = await assemble_subagent_prompt(
        system_content,
        workspace=child_registry.workspace,
        tool_registry=child_registry,
    )

    system_msg = SystemMessage(content=system_prompt)
    user_msg = UserMessage(content=prompt)

    child_state = AgentState(
        messages=[system_msg, user_msg],
        session_id=SessionID(child_session.id),
        usage=SessionUsage(context_size=0),
    )
    return child_state, child_registry


async def map_event_to_subagent_delta(
    task_id: str,
    event: Any,
    sink: Callable[[Any], Awaitable[None]],
) -> int:
    if isinstance(event, TextDelta):
        await sink(SubAgentDelta(id=task_id, kind="text", content=event.text))
    elif isinstance(event, ReasoningDelta):
        await sink(SubAgentDelta(id=task_id, kind="reasoning", content=event.text))
    elif isinstance(event, ToolCall):
        await sink(
            SubAgentDelta(
                id=task_id,
                kind="tool",
                tool_name=event.tool_name,
                tool_input=event.args,
            )
        )
        return 1
    elif isinstance(event, ToolResult):
        await sink(
            SubAgentDelta(
                id=task_id,
                kind="tool_result",
                tool_name=event.name,
                content=event.result,
            )
        )
    elif isinstance(event, ToolError):
        await sink(
            SubAgentDelta(
                id=task_id,
                kind="tool_result",
                tool_name=event.name,
                content=event.message,
            )
        )
    elif isinstance(
        event, (StepStart, TextStart, TextEnd, ReasoningStart, ReasoningEnd, Compacting)
    ):
        await sink(event)
    return 0
