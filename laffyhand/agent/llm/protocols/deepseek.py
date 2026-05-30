from loguru import logger
from laffyhand.agent.schemas import LLMRequest, StreamFinish, FinishReason, StreamReasoning
from laffyhand.agent.llm.protocols.openai import OpenAIProtocol, OpenAIChatChunk
from typing import cast, get_args


class DeepseekProtocol(OpenAIProtocol):
    def build_request(self, request: LLMRequest) -> dict:
        body = super().build_request(request)
        body["thinking"] = {"type": "enabled"}
        body["reasoning_effort"] = "high"
        logger.debug("DeepSeek extras: thinking=enabled, reasoning_effort=high")
        return body

    def parse_frame(self, frame: dict) -> list:
        """Override to handle DeepSeek's reasoning_content quirk.

        DeepSeek emits thinking tokens as ``reasoning_content`` with an
        empty ``content`` field.  Emit ``StreamReasoning`` events for
        thinking tokens, so the UI can display them separately.
        Falls through to the standard OpenAI parser for frames that have
        actual content (e.g. the response phase or non-thinking models).
        """
        chunk = OpenAIChatChunk.model_validate(frame)
        if chunk.choices:
            delta = chunk.choices[0].delta
            if delta.reasoning_content and not delta.content:
                events: list = []
                events.append(StreamReasoning(delta=delta.reasoning_content))
                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason
                    usage = self._openai_usage_to_internal(chunk.usage) if chunk.usage else None
                    if finish_reason not in get_args(FinishReason):
                        finish_reason = "other"
                    events.append(StreamFinish(finish_reason=cast(FinishReason, finish_reason), usage=usage))
                return events
        return super().parse_frame(frame)
