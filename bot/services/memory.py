from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import settings
from bot.database.repositories import MessageRepository, FactRepository, AvatarRepository
from bot.services.fact_extractor import extract_facts_background
from bot.utils.text import escape_html

if TYPE_CHECKING:
    from bot.services.llm import LLMService

logger = logging.getLogger(__name__)


class MemoryService:
    """Orchestrates short-term and long-term memory."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.message_repo = MessageRepository(session)
        self.fact_repo = FactRepository(session)
        self.avatar_repo = AvatarRepository(session)

    async def save_message(
        self,
        user_id: int,
        avatar_id: int,
        role: str,
        content: str,
    ) -> None:
        """Save a message to the dialog history (short-term memory)."""
        await self.message_repo.add_message(
            user_id=user_id,
            avatar_id=avatar_id,
            role=role,
            content=content,
        )

    async def build_prompt(
        self,
        user_id: int,
        avatar_id: int,
    ) -> list[dict[str, str]]:
        """Build the complete prompt for the LLM call.

        Expects the current user message to already be saved in DB
        (so it appears in recent history).

        Structure:
          1. System prompt (avatar personality)
          2. Long-term facts (injected into system context)
          3. Recent messages (short-term memory, includes current message)
        """
        messages: list[dict[str, str]] = []

        # 1. Avatar system prompt
        avatar = await self.avatar_repo.get_by_id(avatar_id)
        system_text = avatar.system_prompt

        # 2. Long-term facts injection
        facts = await self.fact_repo.get_facts(
            user_id=user_id, avatar_id=avatar_id
        )
        if facts:
            facts_text = "\n".join(f"- {f.fact_text}" for f in facts)
            system_text += (
                f"\n\nВажно: ты помнишь об этом пользователе следующее:\n{facts_text}"
            )

        messages.append({"role": "system", "content": system_text})

        # 3. Short-term history (includes the just-saved current message)
        recent = await self.message_repo.get_recent_messages(
            user_id=user_id,
            avatar_id=avatar_id,
            limit=settings.short_term_message_limit,
        )
        for msg in recent:
            messages.append({"role": msg.role, "content": msg.content})

        return messages

    async def maybe_extract_facts(
        self,
        user_id: int,
        avatar_id: int,
        llm: LLMService,
        session_factory: async_sessionmaker[AsyncSession],
        bot: Bot | None = None,
        chat_id: int | None = None,
    ) -> None:
        """Trigger background fact extraction if message count threshold is reached.

        Uses a DB-based counter (messages since last extraction) so it
        survives restarts and works across multiple instances.
        If bot and chat_id are provided, sends a notification about new facts.
        """
        count = await self.message_repo.count_messages_since_last_extraction(
            user_id=user_id,
            avatar_id=avatar_id,
        )

        if count >= settings.fact_extraction_interval:
            asyncio.create_task(
                _extract_and_notify(
                    user_id, avatar_id, session_factory, llm, bot, chat_id,
                )
            )


async def _extract_and_notify(
    user_id: int,
    avatar_id: int,
    session_factory: "async_sessionmaker",
    llm: "LLMService",
    bot: Bot | None,
    chat_id: int | None,
) -> None:
    """Run fact extraction and send a notification if new facts were found."""
    new_facts = await extract_facts_background(
        user_id, avatar_id, session_factory, llm,
    )
    if new_facts and bot and chat_id:
        try:
            facts_list = ", ".join(escape_html(f) for f in new_facts[:3])
            suffix = f" и ещё {len(new_facts) - 3}" if len(new_facts) > 3 else ""
            await bot.send_message(
                chat_id,
                f"\U0001f9e0 Запомнил: {facts_list}{suffix}",
            )
        except Exception:
            logger.debug("Failed to send fact notification to chat %s", chat_id)
