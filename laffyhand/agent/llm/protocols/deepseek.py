from typing import Any

from loguru import logger
from laffyhand.agent.llm.specs.models import LLMRequest
from laffyhand.agent.schemas import StreamReasoning, LLMEvent
from laffyhand.agent.llm.protocols.openai import OpenAIProtocol, OpenAIChatChunk


class DeepseekProtocol(OpenAIProtocol):
    def build_request(self, request: LLMRequest) -> dict[str, Any]:
        body = super().build_request(request).model_dump()
        body["thinking"] = {"type": "enabled"}
        body["reasoning_effort"] = "high"
        logger.debug("DeepSeek extras: thinking=enabled, reasoning_effort=high")
        return body

    def parse_frame(self, frame: dict[str, Any]) -> list[LLMEvent]:
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
            logger.trace(
                f"DeepSeek reasoning_content={delta.reasoning_content[:100] if delta.reasoning_content else None}"
            )
            events: list[LLMEvent] = []
            if delta.reasoning_content:
                events.append(StreamReasoning(delta=delta.reasoning_content))
            parent_events = super().parse_frame(frame)
            events.extend(
                e for e in parent_events if not isinstance(e, StreamReasoning)
            )
            if events:
                return events
            return parent_events
        return super().parse_frame(frame)
