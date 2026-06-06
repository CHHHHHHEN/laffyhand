from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from laffyhand.core.runtime import AgentRuntime
    from laffyhand.gateway.transport import Transport


async def handle_tools_list(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    tools = await runtime.tool_registry.build_tool_definitions()
    session_id: str | None = params.get("session_id")
    state = runtime.get_state(session_id) if session_id else None
    disabled = state.disabled_tools if state else set()
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "enabled": t.name not in disabled,
            }
            for t in tools
        ],
    }


async def handle_tools_set_disabled(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    tool_names: list[str] = params.get("tool_names", [])
    session_id: str | None = params.get("session_id")
    if not session_id:
        raise ValueError("session_id is required")
    state = runtime.get_state(session_id)
    if state is None:
        raise RuntimeError(f"Session not found: {session_id}")
    state.disabled_tools = set(tool_names)
    return {"status": "ok", "disabled_tools": tool_names}


async def handle_workspace_set(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    workspace: str = params.get("workspace", "")
    if not workspace:
        return {"error": "workspace path is required"}
    resolved = str(Path(workspace).resolve())
    if not os.path.isdir(resolved):
        return {"error": f"workspace path does not exist: {workspace}"}
    runtime.tool_registry.workspace = resolved
    logger.info(f"Workspace set to {resolved} (conn={conn_id})")
    return {"workspace": resolved}
