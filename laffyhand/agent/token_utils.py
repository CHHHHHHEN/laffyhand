from laffyhand.agent.llm.specs.models import (
    AssistantMessage, Message, SystemMessage, ToolMessage, UserMessage,
)


CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(0, round(len(text) / CHARS_PER_TOKEN))


def estimate_message_tokens(msg: Message) -> int:
    total = 0
    if isinstance(msg, (SystemMessage, UserMessage)):
        total += estimate_tokens(msg.content)
    elif isinstance(msg, AssistantMessage):
        if msg.content:
            total += estimate_tokens(msg.content)
        if msg.reasoning:
            total += estimate_tokens(msg.reasoning)
        if msg.tool_calls:
            for tc in msg.tool_calls:
                total += estimate_tokens(tc.tool_name + tc.args)
    elif isinstance(msg, ToolMessage):
        total += estimate_tokens(msg.content)
    return total


def estimate_messages_tokens(messages: list[Message]) -> int:
    return sum(estimate_message_tokens(m) for m in messages)
