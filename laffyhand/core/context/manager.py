from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from loguru import logger
from pydantic import BaseModel, Field

from laffyhand.core.context.chain import (
    compact_with_chain,
    is_overflow,
    select_tail,
)
from laffyhand.core.context._prune import prune
from laffyhand.core.llm.specs.models import Message, SystemMessage, UserMessage
from laffyhand.core.models import AgentState, CompactionConfig, SessionID
from laffyhand.core._utils import estimate_messages_tokens

if TYPE_CHECKING:
    from laffyhand.core.llm.facade import LLM
    from laffyhand.core.session import SessionManager


class PreparedContext(BaseModel):
    messages: list[Message] = Field(default_factory=list)
    compacted: bool = False
    session_id: str | None = None


class ContextManager:
    def __init__(
        self,
        llm: LLM,
        config: CompactionConfig,
        session_manager: SessionManager | None = None,
        on_compacted: Callable[[str], None] | None = None,
    ) -> None:
        self._llm = llm
        self._config = config
        self._session_manager = session_manager
        self._on_compacted = on_compacted
        self._compacted_this_step = False

    async def prepare(self, state: AgentState) -> PreparedContext:
        context_size = state.usage.context_size
        if not context_size:
            return PreparedContext(messages=state.messages)

        messages = state.messages
        if self._config.prune:
            messages = prune(
                messages,
                curr_context_usage=state.usage.curr_context_usage,
                context_size=context_size,
                config=self._config,
            )

        reserved = self._config.reserved or min(
            self._config.reserved_buffer, context_size // 4
        )
        tokens = state.usage.curr_context_usage or estimate_messages_tokens(messages)
        if is_overflow(tokens, context_size, reserved) and not self._compacted_this_step:
            head, tail = select_tail(messages, self._config, context_size)
            if head:
                self._compacted_this_step = True
                compacted = await self._do_compact(state)
                if compacted:
                    logger.info(f"Pre-turn compaction resolved overflow ({tokens} tokens)")
                    return PreparedContext(
                        messages=state.messages,
                        compacted=True,
                        session_id=str(state.session_id),
                    )

        return PreparedContext(messages=messages)

    async def _do_compact(self, state: AgentState) -> bool:
        if self._session_manager is None or not state.session_id:
            logger.error("Compaction requires a session_manager")
            return False

        result = await compact_with_chain(state, self._llm, self._config)
        if result is None:
            return False

        summary, original_system, tail = result
        child = self._session_manager.create_compacted_child(
            parent_id=state.session_id,
            system_messages=original_system,
            summary_content=summary,
            tail_messages=tail,
        )
        summary_msg = SystemMessage(content=summary.strip())
        state.session_id = SessionID(child.id)
        state.messages = original_system + [summary_msg] + tail
        state.step = 0
        if self._on_compacted is not None:
            self._on_compacted(child.id)
        return True

    async def post_turn(self, state: AgentState) -> bool:
        if self._compacted_this_step:
            self._compacted_this_step = False
            return False

        compacted = await self._do_compact(state)
        if not compacted:
            return False

        logger.info("Post-turn compaction completed")
        if self._config.auto_continue:
            state.messages.append(
                UserMessage(
                    content="Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed.",
                )
            )
            logger.info("Auto-continue injected after post-turn compaction")
            return True
        return False

    def reset_step_flag(self) -> None:
        self._compacted_this_step = False
