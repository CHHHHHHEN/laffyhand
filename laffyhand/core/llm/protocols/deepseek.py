from typing import Any, ClassVar, Literal
from pydantic import BaseModel
from loguru import logger
from laffyhand.core.domain.messages import ProviderID
from laffyhand.core.llm.specs.models import LLMRequest, Frame
from laffyhand.core.llm.specs.models import StreamReasoning, LLMEvent
from laffyhand.core.llm.protocols.openai import (
    OpenAIProtocol,
    OpenAIChatChunk,
    OpenAICompletionRequest,
)


class DeepSeekThinking(BaseModel):
    type: Literal["enabled", "disabled"] = "enabled"
    reasoning_effort: Literal["high", "max"] = "high"


class DeepSeekCompletionRequest(OpenAICompletionRequest):
    thinking: DeepSeekThinking | None = None


class DeepseekProtocol(OpenAIProtocol):
    provider_id: ClassVar[ProviderID] = ProviderID("deepseek")

    def build_request(self, request: LLMRequest) -> DeepSeekCompletionRequest:
        base = super().build_request(request)
        return DeepSeekCompletionRequest(
            **base.model_dump(), thinking=DeepSeekThinking()
        )

    def parse_frame(self, frame: Frame | dict[str, Any]) -> list[LLMEvent]:
        if isinstance(frame, dict):
            frame = Frame(data=frame)
        chunk = OpenAIChatChunk.model_validate(frame.data)
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
