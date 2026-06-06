from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from laffyhand.core.runtime import AgentRuntime
    from laffyhand.gateway.transport import Transport


async def handle_config_providers(
    runtime: AgentRuntime,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    providers = {}
    for key, pc in runtime.config.llm.providers.items():
        providers[key] = {
            "type": pc.type,
            "base_url": pc.base_url,
            "models": [
                {"name": m.name, "context_size": m.context_size} for m in pc.models
            ],
        }
    logger.debug(
        f"config/providers: returning {len(providers)} provider(s) (conn={conn_id})"
    )
    return {
        "default_provider": runtime.config.llm.default_provider,
        "providers": providers,
    }
