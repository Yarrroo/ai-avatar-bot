from sqlalchemy import delete, func, select

from bot.database.models import DialogMessage, MemoryFact
from bot.database.repositories.base import BaseRepository


class MessageRepository(BaseRepository):

    async def add_message(
        self,
        user_id: int,
        avatar_id: int,
        role: str,
        content: str,
    ) -> DialogMessage:
        msg = DialogMessage(
            user_id=user_id,
            avatar_id=avatar_id,
            role=role,
            content=content,
        )
        self._session.add(msg)
        await self._session.flush()
        return msg

    async def get_recent_messages(
        self,
        user_id: int,
        avatar_id: int,
        limit: int = 10,
    ) -> list[DialogMessage]:
        subq = (
            select(DialogMessage.id)
            .where(
                DialogMessage.user_id == user_id,
                DialogMessage.avatar_id == avatar_id,
            )
            .order_by(DialogMessage.created_at.desc())
            .limit(limit)
            .subquery()
        )
        stmt = (
            select(DialogMessage)
            .where(DialogMessage.id.in_(select(subq.c.id)))
            .order_by(DialogMessage.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_messages_since_last_extraction(
        self,
        user_id: int,
        avatar_id: int,
    ) -> int:
        """Count user messages added since the most recent fact extraction."""
        # Find the latest fact's created_at as the extraction boundary
        latest_fact_stmt = (
            select(func.max(MemoryFact.created_at))
            .where(
                MemoryFact.user_id == user_id,
                MemoryFact.avatar_id == avatar_id,
            )
        )
        result = await self._session.execute(latest_fact_stmt)
        latest_fact_time = result.scalar()

        count_stmt = (
            select(func.count())
            .select_from(DialogMessage)
            .where(
                DialogMessage.user_id == user_id,
                DialogMessage.avatar_id == avatar_id,
                DialogMessage.role == "user",
            )
        )
        if latest_fact_time is not None:
            count_stmt = count_stmt.where(
                DialogMessage.created_at > latest_fact_time,
            )

        result = await self._session.execute(count_stmt)
        return result.scalar() or 0

    async def clear_history(self, user_id: int, avatar_id: int) -> int:
        stmt = (
            delete(DialogMessage)
            .where(
                DialogMessage.user_id == user_id,
                DialogMessage.avatar_id == avatar_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.rowcount
