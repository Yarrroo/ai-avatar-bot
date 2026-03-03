from sqlalchemy import delete, select

from bot.database.models import DialogMessage
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
