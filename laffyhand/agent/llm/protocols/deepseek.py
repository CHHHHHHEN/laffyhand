from loguru import logger
from laffyhand.agent.schemas import LLMRequest
from laffyhand.agent.llm.protocols.openai import OpenAIProtocol


class DeepseekProtocol(OpenAIProtocol):
    def build_request(self, request: LLMRequest) -> dict:
        body = super().build_request(request)
        body["thinking"] = {"type": "enabled"}
        body["reasoning_effort"] = "high"
        logger.debug("DeepSeek extras: thinking=enabled, reasoning_effort=high")
        return body
