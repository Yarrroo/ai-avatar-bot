from sqlalchemy import func, select, update

from bot.database.models import MemoryFact
from bot.database.repositories.base import BaseRepository

FACTS_PER_PAGE = 10


class FactRepository(BaseRepository):

    async def get_facts(
        self,
        user_id: int,
        avatar_id: int,
    ) -> list[MemoryFact]:
        stmt = (
            select(MemoryFact)
            .where(
                MemoryFact.user_id == user_id,
                MemoryFact.avatar_id == avatar_id,
                MemoryFact.is_active.is_(True),
            )
            .order_by(MemoryFact.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_facts_page(
        self,
        user_id: int,
        avatar_id: int,
        page: int = 0,
        per_page: int = FACTS_PER_PAGE,
    ) -> tuple[list[MemoryFact], int]:
        """Get paginated active facts. Returns (facts, total_count)."""
        count_stmt = (
            select(func.count())
            .select_from(MemoryFact)
            .where(
                MemoryFact.user_id == user_id,
                MemoryFact.avatar_id == avatar_id,
                MemoryFact.is_active.is_(True),
            )
        )
        total = (await self._session.execute(count_stmt)).scalar() or 0

        stmt = (
            select(MemoryFact)
            .where(
                MemoryFact.user_id == user_id,
                MemoryFact.avatar_id == avatar_id,
                MemoryFact.is_active.is_(True),
            )
            .order_by(MemoryFact.created_at.asc())
            .offset(page * per_page)
            .limit(per_page)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def deactivate_fact(
        self,
        fact_id: int,
        user_id: int,
    ) -> bool:
        """Soft-delete a fact (set is_active=False). Returns True if updated."""
        stmt = (
            update(MemoryFact)
            .where(
                MemoryFact.id == fact_id,
                MemoryFact.user_id == user_id,
                MemoryFact.is_active.is_(True),
            )
            .values(is_active=False)
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0

    async def deactivate_similar(
        self,
        user_id: int,
        avatar_id: int,
        texts: list[str],
        threshold: float = 0.75,
    ) -> int:
        """Deactivate facts that are similar to any of the given texts."""
        from difflib import SequenceMatcher

        facts = await self.get_facts(user_id, avatar_id)
        deactivated = 0
        for fact in facts:
            for text in texts:
                ratio = SequenceMatcher(
                    None, fact.fact_text.lower(), text.lower()
                ).ratio()
                if ratio > threshold:
                    fact.is_active = False
                    deactivated += 1
                    break
        return deactivated

