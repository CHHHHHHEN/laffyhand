from __future__ import annotations

import asyncio
from collections.abc import Callable

from loguru import logger

from laffyhand.core.domain.messages import Message, SystemMessage, UserMessage
from laffyhand.core.session.models import TitleConfig
from laffyhand.core.llm.facade import LLM, stream_text
from laffyhand.core.session.manager import SessionManager
from laffyhand.core.exceptions import ConfigError


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
    result = await stream_text(llm, title_messages)
    if result is None:
        logger.error("Title generation stream error")
        return None
    title = result.strip().strip('"').strip("'")
    if not title:
        return None
    session_manager.set_title(session_id, title)
    logger.info(f"Title generated for {session_id}: {title}")
    return title


class TitleService:
    """Manages title generation lifecycle: gating, scheduling, and LLM generation."""

    def __init__(
        self,
        session_manager: SessionManager,
        title_config: TitleConfig | None = None,
        llm_provider: Callable[[str], LLM] | None = None,
    ) -> None:
        self.session_manager = session_manager
        self.title_config = title_config or TitleConfig()
        self._llm_provider = llm_provider

    def should_generate(self, session_id: str, trigger: str) -> bool:
        if self.title_config.mode == "off":
            return False
        if self.title_config.mode != trigger:
            return False
        session = self.session_manager.get(session_id)
        if session is None:
            session = self.session_manager.ensure_exists(session_id)
        return session is not None and not session.title

    def schedule_generation(self, session_id: str, trigger: str) -> None:
        if not self.should_generate(session_id, trigger):
            return
        asyncio.create_task(self._do_generate_title(session_id))

    async def generate_title(
        self, session_id: str, llm: LLM | None = None
    ) -> str | None:
        return await self._do_generate_title(session_id, llm=llm)

    async def _do_generate_title(
        self, session_id: str, llm: LLM | None = None
    ) -> str | None:
        try:
            if llm is None:
                if self._llm_provider is None:
                    raise ConfigError("TitleService: llm_provider not set")
                llm = self._llm_provider(session_id)
            title = await asyncio.wait_for(
                generate_title(
                    self.session_manager, session_id, llm, self.title_config
                ),
                timeout=30,
            )
            if title:
                logger.info(f"Auto-generated title for session {session_id}: {title}")
            else:
                logger.warning(
                    f"Title generator returned empty for session {session_id}"
                )
            return title
        except asyncio.TimeoutError:
            logger.warning(f"Title generation timed out for session {session_id}")
            return None
        except Exception:
            logger.exception(f"Title generation failed for session {session_id}")
            return None


__all__ = ["generate_title", "TitleService"]
