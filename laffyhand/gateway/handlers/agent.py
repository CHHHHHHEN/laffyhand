from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from laffyhand.core.runtime import AgentRuntime
    from laffyhand.gateway.transport import Transport


async def handle_agent_list(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    agents = runtime.agent_registry.list_visible()
    return {
        "agents": [
            {
                "name": a.name,
                "description": a.description,
                "mode": a.mode,
                "system_prompt": a.system_prompt,
                "model": a.model,
            }
            for a in agents
        ],
    }


async def handle_subagent_list_active(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str | None = params.get("session_id")
    if not session_id:
        return {"subagents": []}
    return {"subagents": runtime.subagent_manager.list_active(session_id)}
