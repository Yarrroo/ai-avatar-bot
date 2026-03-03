import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.repositories import MessageRepository, FactRepository, AvatarRepository
from bot.services.fact_extractor import extract_facts_background

logger = logging.getLogger(__name__)

# In-memory counter for fact extraction triggers: (user_id, avatar_id) -> count
_extraction_counters: dict[tuple[int, int], int] = {}


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
        llm: "LLMService",
        session_factory: "async_sessionmaker",
    ) -> None:
        """Trigger background fact extraction if message count threshold is reached.

        Uses an in-memory counter per (user_id, avatar_id) pair.
        On trigger, spawns a background task with its own DB session.
        """
        key = (user_id, avatar_id)
        _extraction_counters[key] = _extraction_counters.get(key, 0) + 1

        if _extraction_counters[key] >= settings.fact_extraction_interval:
            _extraction_counters[key] = 0
            # Fire and forget — do not block the user response
            asyncio.create_task(
                extract_facts_background(user_id, avatar_id, session_factory, llm)
            )
