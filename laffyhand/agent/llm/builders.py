from loguru import logger
from laffyhand.agent.llm.protocols.openai import OpenAIProtocol, OpenAIEndpoint
from laffyhand.agent.llm.protocols.deepseek import DeepseekProtocol
from laffyhand.agent.llm._bearer_auth import BearerAuth
from laffyhand.agent.llm._sse_framing import SSEFraming
from laffyhand.agent.llm._route import Route


def openai_route(base_url: str, api_key: str) -> Route:
    # api_key is intentionally not logged to avoid credential leakage
    logger.debug(f"Building OpenAI route: base_url={base_url}")
    return Route(
        protocol=OpenAIProtocol(),
        endpoint=OpenAIEndpoint(base_url=base_url),
        auth=BearerAuth(api_key=api_key),
        framing=SSEFraming(),
    )


def deepseek_route(base_url: str, api_key: str) -> Route:
    # api_key is intentionally not logged to avoid credential leakage
    logger.debug(f"Building DeepSeek route: base_url={base_url}")
    return Route(
        protocol=DeepseekProtocol(),
        endpoint=OpenAIEndpoint(base_url=base_url),
        auth=BearerAuth(api_key=api_key),
        framing=SSEFraming(),
    )
