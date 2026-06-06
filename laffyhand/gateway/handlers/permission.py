from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from laffyhand.core.runtime import AgentRuntime
    from laffyhand.gateway.transport import Transport


async def handle_permission_respond(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    req_id: str = params.get("request_id", "")
    if req_id not in runtime.session_store.pending_permissions:
        raise ValueError(f"Unknown or expired permission request: {req_id}")
    action: str = params.get("action", "")
    if action not in ("allow", "always", "deny"):
        raise ValueError(f"Invalid permission action: {action}")
    reason: str | None = params.get("reason")
    event, permission, pattern, _, _ = runtime.session_store.pending_permissions[req_id]
    if action == "always":
        runtime.tool_registry.permission.add_rule(f"{permission}:{pattern}", "allow")
        result = True
    elif action == "allow":
        result = True
    else:
        result = False
    runtime.session_store.pending_permissions[req_id] = (event, permission, pattern, result, reason)
    event.set()
    logger.info(
        f"Permission '{permission}:{pattern}' resolved: {action} (conn={conn_id})"
    )
    return {"status": "ok"}
