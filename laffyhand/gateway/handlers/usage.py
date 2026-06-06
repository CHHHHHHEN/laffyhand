from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from laffyhand.core.runtime import AgentRuntime
    from laffyhand.gateway.transport import Transport


async def handle_usage_get(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    session_id: str | None = params.get("session_id")
    if not session_id:
        return {
            "curr_context_usage": 0,
            "total_input": 0,
            "total_output": 0,
            "total_reasoning": 0,
            "context_size": 0,
        }
    state = runtime.get_state(session_id)
    if state is None or state.usage is None:
        return {
            "curr_context_usage": 0,
            "total_input": 0,
            "total_output": 0,
            "total_reasoning": 0,
            "context_size": 0,
        }
    return {
        "curr_context_usage": state.usage.curr_context_usage,
        "total_input": state.usage.total_input,
        "total_output": state.usage.total_output,
        "total_reasoning": state.usage.total_reasoning,
        "context_size": state.usage.context_size,
    }
