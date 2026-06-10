from loguru import logger

from laffyhand.llm._route import Route
from laffyhand.llm._bearer_auth import BearerAuth
from laffyhand.llm._sse_framing import SSEFraming
from laffyhand.llm.protocols.openai import OpenAIProtocol, OpenAIEndpoint
from laffyhand.llm.protocols.deepseek import DeepseekProtocol
from laffyhand.llm.specs.protocol import Protocol

_PROTOCOLS: list[type[Protocol]] = [OpenAIProtocol, DeepseekProtocol]


def build_route(provider_type: str, base_url: str, api_key: str) -> Route:
    for cls in _PROTOCOLS:
        if cls.provider_id == provider_type:
            protocol_cls = cls
            break
    else:
        supported = sorted(p.provider_id for p in _PROTOCOLS)
        raise ValueError(
            f"Unsupported provider type {provider_type!r}. Supported: {supported}"
        )
    logger.debug(f"Building route: type={provider_type}, base_url={base_url}")
    return Route(
        protocol=protocol_cls(),
        endpoint=OpenAIEndpoint(base_url=base_url),
        auth=BearerAuth(api_key=api_key),
        framing=SSEFraming(),
    )
