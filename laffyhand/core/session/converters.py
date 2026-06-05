from __future__ import annotations


from laffyhand.core.llm.specs.models import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolCallContent,
    ToolMessage,
    Usage,
    UserMessage,
)
from laffyhand.core.session.models import (
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
from laffyhand.core.llm.specs.models import ModelID, ProviderID
from laffyhand.core.session.models import generate_id, utcnow


def message_to_session_message(msg: Message, session_id: str) -> SessionMessage:
    now = int(utcnow().timestamp() * 1000)
    if isinstance(msg, SystemMessage):
        return SessionMessage(
            id=generate_id(), session_id=session_id, type="synthetic",
            time_created=now, time_updated=now,
            data=SyntheticData(session_id=session_id, text=msg.content),
        )
    if isinstance(msg, UserMessage):
        return SessionMessage(
            id=generate_id(), session_id=session_id, type="user",
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
            id=generate_id(), session_id=session_id, type="assistant",
            time_created=now, time_updated=now,
            data=AssistantData(
                agent="", model=Model(id=ModelID(""), provider=ProviderID("")),
                snapshot=MessageSnapshot(), finish="stop", cost=0, tokens=tokens,
                content=content,
            ),
        )
    if isinstance(msg, ToolMessage):
        command = f"{msg.tool_name} {msg.args}" if msg.tool_name else ""
        return SessionMessage(
            id=generate_id(), session_id=session_id, type="shell",
            time_created=now, time_updated=now,
            data=ShellData(
                callID=msg.tool_call_id, command=command, output=msg.content,
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
