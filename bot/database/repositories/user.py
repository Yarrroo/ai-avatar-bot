from sqlalchemy import select, update

from bot.database.models import User
from bot.database.repositories.base import BaseRepository


class UserRepository(BaseRepository):

    async def get_or_create(self, user_id: int) -> User:
        stmt = select(User).where(User.user_id == user_id)
        result = await self._session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            user = User(user_id=user_id)
            self._session.add(user)
            await self._session.flush()

        return user

    async def update_avatar(self, user_id: int, avatar_id: int | None) -> None:
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(current_avatar_id=avatar_id)
        )
        await self._session.execute(stmt)
