from loguru import logger
from laffyhand.agent.schemas import LLMRequest, StreamReasoning
from laffyhand.agent.llm.protocols.openai import OpenAIProtocol, OpenAIChatChunk


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
        # Debug: log raw frame for first few frames
        logger.debug(f"DeepSeek raw frame: {frame}")
        chunk = OpenAIChatChunk.model_validate(frame)
        if chunk.choices:
            delta = chunk.choices[0].delta
            # Debug: log delta fields
            logger.debug(f"DeepSeek delta: content={delta.content[:100] if delta.content else None}, reasoning_content={delta.reasoning_content[:100] if delta.reasoning_content else None}")
            # Debug: log raw delta fields
            logger.debug(f"DeepSeek delta keys: {list(delta.model_fields_set)}")
            # Always emit StreamReasoning if reasoning_content is present
            events: list = []
            if delta.reasoning_content:
                events.append(StreamReasoning(delta=delta.reasoning_content))
            # Let parent handle content, tool_calls, finish_reason, etc.
            parent_events = super().parse_frame(frame)
            events.extend(parent_events)
            if events:
                return events
        return super().parse_frame(frame)
