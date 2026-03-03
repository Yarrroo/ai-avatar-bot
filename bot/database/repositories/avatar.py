from sqlalchemy import select

from bot.database.models import Avatar
from bot.database.repositories.base import BaseRepository


class AvatarRepository(BaseRepository):

    async def get_all(self) -> list[Avatar]:
        stmt = select(Avatar).order_by(Avatar.id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, avatar_id: int) -> Avatar | None:
        stmt = select(Avatar).where(Avatar.id == avatar_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
