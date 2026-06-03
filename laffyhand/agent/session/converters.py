from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from laffyhand.agent.llm.specs.models import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolCallContent,
    ToolMessage,
    Usage,
    UserMessage,
)
from laffyhand.agent.session.models import (
    AssistantContent,
    AssistantData,
    AssistantReasoningPart,
    AssistantTextPart,
    AssistantToolPart,
    MessageSnapshot,
    MessageTime,
    Model,
    SessionMessage,
    ShellData,
    SyntheticData,
    TokenCache,
    TokenDetail,
    ToolStateCompleted,
    ToolStatePending,
    UserData,
)
from laffyhand.agent.llm.specs.models import ModelID, ProviderID


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _generate_id() -> str:
    now = _utcnow()
    return now.strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]


def message_to_session_message(msg: Message, session_id: str) -> SessionMessage:
    now = int(_utcnow().timestamp() * 1000)
    if isinstance(msg, SystemMessage):
        return SessionMessage(
            id=_generate_id(), session_id=session_id, type="synthetic",
            time_created=now, time_updated=now,
            data=SyntheticData(sessionID=session_id, text=msg.content),
        )
    if isinstance(msg, UserMessage):
        return SessionMessage(
            id=_generate_id(), session_id=session_id, type="user",
            time_created=now, time_updated=now,
            data=UserData(text=msg.content),
        )
    if isinstance(msg, AssistantMessage):
        content: list[AssistantContent] = []
        if msg.reasoning:
            content.append(AssistantReasoningPart(id=f"reasoning-{now}", text=msg.reasoning))
        if msg.content:
            content.append(AssistantTextPart(text=msg.content))
        if msg.tool_calls:
            for tc in msg.tool_calls:
                content.append(AssistantToolPart(
                    id=tc.tool_call_id, name=tc.tool_name,
                    state=ToolStatePending(input=tc.args),
                    time=MessageTime(created=now),
                ))
        tokens = TokenDetail(
            input=msg.tokens.input_tokens or 0, output=msg.tokens.output_tokens or 0,
            reasoning=msg.tokens.reasoning_tokens or 0,
            cache=TokenCache(read=msg.tokens.cache_read_tokens or 0, write=msg.tokens.cache_write_tokens or 0),
        ) if msg.tokens else None
        return SessionMessage(
            id=_generate_id(), session_id=session_id, type="assistant",
            time_created=now, time_updated=now,
            data=AssistantData(
                agent="", model=Model(id=ModelID(""), provider=ProviderID("")),
                snapshot=MessageSnapshot(), finish="stop", cost=0, tokens=tokens,
                content=content,
            ),
        )
    if isinstance(msg, ToolMessage):
        return SessionMessage(
            id=_generate_id(), session_id=session_id, type="shell",
            time_created=now, time_updated=now,
            data=ShellData(
                callID=msg.tool_call_id, command="", output=msg.content,
                is_error=msg.is_error, time=MessageTime(created=now),
            ),
        )
    raise TypeError(f"Unknown message type: {type(msg).__name__}")


def session_message_to_message(sm: SessionMessage) -> Message:
    if sm.type == "synthetic":
        d = sm.data
        assert isinstance(d, SyntheticData)
        return SystemMessage(content=d.text)
    if sm.type == "user":
        d = sm.data
        assert isinstance(d, UserData)
        return UserMessage(content=d.text)
    if sm.type == "assistant":
        d = sm.data
        assert isinstance(d, AssistantData)
        content_parts: list[str] = []
        reasoning: str | None = None
        tool_calls: list[ToolCallContent] | None = None
        for part in d.content:
            if isinstance(part, AssistantTextPart):
                content_parts.append(part.text)
            elif isinstance(part, AssistantReasoningPart):
                reasoning = (reasoning or "") + part.text
            elif isinstance(part, AssistantToolPart):
                if tool_calls is None:
                    tool_calls = []
                if isinstance(part.state, ToolStateCompleted):
                    args = part.state.input.get("input", "") if isinstance(part.state.input, dict) else str(part.state.input)
                    tool_calls.append(ToolCallContent(tool_call_id=part.id, tool_name=part.name, args=args))
                elif isinstance(part.state, ToolStatePending):
                    tool_calls.append(ToolCallContent(tool_call_id=part.id, tool_name=part.name, args=part.state.input))
        combined = "".join(content_parts) if content_parts else None
        usage = Usage(
            input_tokens=d.tokens.input, output_tokens=d.tokens.output,
            reasoning_tokens=d.tokens.reasoning,
            cache_read_tokens=d.tokens.cache.read, cache_write_tokens=d.tokens.cache.write,
        ) if d.tokens else None
        return AssistantMessage(content=combined, reasoning=reasoning, tool_calls=tool_calls, tokens=usage)
    if sm.type == "shell":
        d = sm.data
        assert isinstance(d, ShellData)
        return ToolMessage(tool_call_id=d.callID, content=d.output, is_error=d.is_error)
    raise ValueError(f"Unknown session message type: {sm.type}")
