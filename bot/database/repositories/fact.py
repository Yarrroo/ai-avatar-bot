from sqlalchemy import select

from bot.database.models import MemoryFact
from bot.database.repositories.base import BaseRepository


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
                MemoryFact.is_active == True,  # noqa: E712
            )
            .order_by(MemoryFact.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

