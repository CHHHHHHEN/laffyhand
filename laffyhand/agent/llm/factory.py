from loguru import logger

from laffyhand.agent.llm._route import Route
from laffyhand.agent.llm._bearer_auth import BearerAuth
from laffyhand.agent.llm._sse_framing import SSEFraming
from laffyhand.agent.llm.protocols.openai import OpenAIProtocol, OpenAIEndpoint
from laffyhand.agent.llm.protocols.deepseek import DeepseekProtocol

PROTOCOL_MAP: dict[str, type] = {
    "openai": OpenAIProtocol,
    "deepseek": DeepseekProtocol,
}


def build_route(provider_type: str, base_url: str, api_key: str) -> Route:
    if provider_type not in PROTOCOL_MAP:
        raise ValueError(
            f"Unsupported provider type {provider_type!r}. "
            f"Supported: {sorted(PROTOCOL_MAP)}"
        )
    protocol_cls = PROTOCOL_MAP[provider_type]
    logger.debug(f"Building route: type={provider_type}, base_url={base_url}")
    return Route(
        protocol=protocol_cls(),
        endpoint=OpenAIEndpoint(base_url=base_url),
        auth=BearerAuth(api_key=api_key),
        framing=SSEFraming(),
    )
