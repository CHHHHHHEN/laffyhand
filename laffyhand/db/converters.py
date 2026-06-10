from __future__ import annotations

from laffyhand.core._utils.time import generate_id, utcnow
from laffyhand.core.domain.messages import (
    AgentSwitchedMessage,
    AssistantMessage,
    CompactionMessage,
    Message,
    ModelSwitchedMessage,
    SystemMessage,
    ToolCallContent,
    ToolMessage,
    Usage,
    UserMessage,
)
from laffyhand.db.models.message import (
    AgentSwitchedData,
    AssistantContent,
    AssistantData,
    AssistantReasoningPart,
    AssistantTextPart,
    AssistantToolPart,
    CompactionData,
    MessageSnapshot,
    MessageTime,
    ModelSwitchedData,
    SessionMessage,
    ShellData,
    SyntheticData,
    TokenCache,
    TokenDetail,
    ToolStateCompleted,
    ToolStatePending,
    UserData,
)


def message_to_session_message(msg: Message, session_id: str) -> SessionMessage:
    now = int(utcnow().timestamp() * 1000)

    if isinstance(msg, SystemMessage):
        return SessionMessage(
            id=generate_id(),
            session_id=session_id,
            type="synthetic",
            time_created=now,
            time_updated=now,
            data=SyntheticData(session_id=session_id, text=msg.content),
        )

    if isinstance(msg, UserMessage):
        return SessionMessage(
            id=generate_id(),
            session_id=session_id,
            type="user",
            time_created=now,
            time_updated=now,
            data=UserData(
                text=msg.content,
                files=msg.files,
                agents=msg.agents,
                references=msg.references,
            ),
        )

    if isinstance(msg, AssistantMessage):
        content_list: list[AssistantContent] = []
        if msg.reasoning:
            content_list.append(
                AssistantReasoningPart(id=f"reasoning-{now}", text=msg.reasoning),
            )
        if msg.content:
            content_list.append(AssistantTextPart(text=msg.content))
        if msg.tool_calls:
            for tc in msg.tool_calls:
                content_list.append(
                    AssistantToolPart(
                        id=tc.tool_call_id,
                        name=tc.tool_name,
                        state=ToolStatePending(input=tc.args),
                        time=MessageTime(created=now),
                    ),
                )
        tokens = (
            TokenDetail(
                input=msg.tokens.input_tokens or 0,
                output=msg.tokens.output_tokens or 0,
                reasoning=msg.tokens.reasoning_tokens or 0,
                cache=TokenCache(
                    read=msg.tokens.cache_read_tokens or 0,
                    write=msg.tokens.cache_write_tokens or 0,
                ),
            )
            if msg.tokens
            else None
        )
        return SessionMessage(
            id=generate_id(),
            session_id=session_id,
            type="assistant",
            time_created=now,
            time_updated=now,
            data=AssistantData(
                agent=msg.agent,
                model=msg.model_info,
                content=content_list,
                snapshot=MessageSnapshot(),
                finish=msg.finish_reason,
                cost=msg.cost,
                tokens=tokens,
            ),
        )

    if isinstance(msg, ToolMessage):
        if msg.tool_name:
            args_part = msg.args if msg.args is not None else ""
            command = f"{msg.tool_name} {args_part}"
        else:
            command = ""
        return SessionMessage(
            id=generate_id(),
            session_id=session_id,
            type="shell",
            time_created=now,
            time_updated=now,
            data=ShellData(
                callID=msg.tool_call_id,
                command=command,
                output=msg.content,
                is_error=msg.is_error,
                time=MessageTime(created=now),
            ),
        )

    if isinstance(msg, CompactionMessage):
        return SessionMessage(
            id=generate_id(),
            session_id=session_id,
            type="compaction",
            time_created=now,
            time_updated=now,
            data=CompactionData(
                reason=msg.reason,
                summary=msg.summary,
                child_session_id=msg.child_session_id,
            ),
        )

    if isinstance(msg, AgentSwitchedMessage):
        return SessionMessage(
            id=generate_id(),
            session_id=session_id,
            type="agent-switched",
            time_created=now,
            time_updated=now,
            data=AgentSwitchedData(agent=msg.agent),
        )

    if isinstance(msg, ModelSwitchedMessage):
        return SessionMessage(
            id=generate_id(),
            session_id=session_id,
            type="model-switched",
            time_created=now,
            time_updated=now,
            data=ModelSwitchedData(model=msg.model),
        )

    raise TypeError(f"Unknown message type: {type(msg).__name__}")


def _decompose_command(command: str) -> tuple[str | None, str | None]:
    if not command or not command.strip():
        return None, None
    parts = command.split(maxsplit=1)
    tool_name = parts[0]
    args = parts[1] if len(parts) > 1 else ""
    return tool_name, args


def session_message_to_message(sm: SessionMessage) -> Message:
    if sm.type == "synthetic":
        d = sm.data
        if not isinstance(d, SyntheticData):
            raise TypeError(f"Expected SyntheticData, got {type(d).__name__}")
        return SystemMessage(content=d.text)

    if sm.type == "user":
        d = sm.data
        if not isinstance(d, UserData):
            raise TypeError(f"Expected UserData, got {type(d).__name__}")
        return UserMessage(
            content=d.text,
            files=d.files,
            agents=d.agents,
            references=d.references,
        )

    if sm.type == "assistant":
        d = sm.data
        if not isinstance(d, AssistantData):
            raise TypeError(f"Expected AssistantData, got {type(d).__name__}")
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
                    args_val = (
                        part.state.input.get("input", "")
                        if isinstance(part.state.input, dict)
                        else str(part.state.input)
                    )
                    tool_calls.append(
                        ToolCallContent(
                            tool_call_id=part.id,
                            tool_name=part.name,
                            args=args_val,
                        ),
                    )
                elif isinstance(part.state, ToolStatePending):
                    tool_calls.append(
                        ToolCallContent(
                            tool_call_id=part.id,
                            tool_name=part.name,
                            args=part.state.input,
                        ),
                    )

        combined = "".join(content_parts) if content_parts else None
        usage = (
            Usage(
                input_tokens=d.tokens.input,
                output_tokens=d.tokens.output,
                reasoning_tokens=d.tokens.reasoning,
                cache_read_tokens=d.tokens.cache.read,
                cache_write_tokens=d.tokens.cache.write,
            )
            if d.tokens
            else None
        )
        return AssistantMessage(
            content=combined,
            reasoning=reasoning,
            tool_calls=tool_calls,
            tokens=usage,
            agent=d.agent,
            model_info=d.model,
            finish_reason=d.finish,
            cost=d.cost,
        )

    if sm.type == "shell":
        d = sm.data
        if not isinstance(d, ShellData):
            raise TypeError(f"Expected ShellData, got {type(d).__name__}")
        tool_name, args = _decompose_command(d.command)
        return ToolMessage(
            tool_call_id=d.callID,
            content=d.output,
            is_error=d.is_error,
            tool_name=tool_name,
            args=args,
        )

    if sm.type == "compaction":
        d = sm.data
        if not isinstance(d, CompactionData):
            raise TypeError(f"Expected CompactionData, got {type(d).__name__}")
        return CompactionMessage(
            reason=d.reason,
            summary=d.summary,
            child_session_id=d.child_session_id,
        )

    if sm.type == "agent-switched":
        d = sm.data
        if not isinstance(d, AgentSwitchedData):
            raise TypeError(f"Expected AgentSwitchedData, got {type(d).__name__}")
        return AgentSwitchedMessage(agent=d.agent)

    if sm.type == "model-switched":
        d = sm.data
        if not isinstance(d, ModelSwitchedData):
            raise TypeError(f"Expected ModelSwitchedData, got {type(d).__name__}")
        return ModelSwitchedMessage(model=d.model)

    raise ValueError(f"Unknown session message type: {sm.type}")
