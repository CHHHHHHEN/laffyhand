from loguru import logger

from laffyhand.core.llm.specs.models import Message, SystemMessage, UserMessage
from laffyhand.core.llm.specs.models import (
    StreamError,
    StreamFinish,
    StreamText,
)
from laffyhand.core.session.models import TitleConfig
from laffyhand.core.llm.facade import LLM
from laffyhand.core.session.manager import SessionManager


async def generate_title(
    session_manager: SessionManager,
    session_id: str,
    llm: LLM,
    config: TitleConfig = TitleConfig(),
) -> str | None:
    if config.mode == "off":
        return None
    messages = session_manager.get_messages(session_id, limit=10)
    user_prompts = [m for m in messages if isinstance(m, UserMessage)]
    if not user_prompts:
        logger.debug("No user messages found for title generation")
        return None
    first_prompt = user_prompts[0].content[:500]
    title_messages: list[Message] = [
        SystemMessage(content="You are a helpful assistant. Generate a concise title."),
        UserMessage(content=f"{config.prompt}\n\nConversation start:\n{first_prompt}"),
    ]
    parts: list[str] = []
    async for event in llm.stream(title_messages):
        if isinstance(event, StreamText):
            parts.append(event.delta)
        elif isinstance(event, StreamFinish):
            break
        elif isinstance(event, StreamError):
            logger.error(f"Title generation stream error: {event.error}")
            return None
    title = "".join(parts).strip().strip('"').strip("'")
    if not title:
        return None
    session_manager.set_title(session_id, title)
    logger.info(f"Title generated for {session_id}: {title}")
    return title
