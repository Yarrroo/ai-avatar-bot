from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repositories import AvatarRepository, UserRepository
from bot.keyboards.inline import avatar_selection_keyboard
from bot.keyboards.reply import main_keyboard
from bot.states.dialog import DialogState

if TYPE_CHECKING:
    from bot.database.models import Avatar

logger = logging.getLogger(__name__)

router = Router(name="start")

_DEFAULT_GREETING = "Привет! Давай пообщаемся!"


def _build_welcome_text(avatars: list[Avatar]) -> str:
    """Build welcome message with avatar descriptions."""
    avatar_lines = "\n".join(
        f"  {a.emoji} <b>{a.name}</b>\n     <i>{a.description}</i>" for a in avatars
    )
    return (
        "\U0001f916 <b>Привет! Я — бот с ИИ-аватарами.</b>\n\n"
        "Выбери персонажа — и общайся с ним на любые темы:\n\n"
        f"{avatar_lines}\n\n"
        "\U0001f9e0 Я запоминаю важное из наших разговоров "
        "и помню тебя даже после сброса истории.\n\n"
        "\U0001f447 <b>Выбери аватара:</b>"
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Show welcome message and avatar selection keyboard."""
    user_repo = UserRepository(session)
    await user_repo.get_or_create(message.from_user.id)

    avatar_repo = AvatarRepository(session)
    avatars = await avatar_repo.get_all()

    await state.set_state(DialogState.choosing_avatar)
    await message.answer(
        _build_welcome_text(avatars),
        reply_markup=avatar_selection_keyboard(avatars),
    )


@router.callback_query(DialogState.choosing_avatar, F.data.startswith("select_avatar:"))
async def avatar_chosen(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Handle avatar selection button press."""
    avatar_id = int(callback.data.split(":")[1])

    user_repo = UserRepository(session)
    await user_repo.update_avatar(callback.from_user.id, avatar_id)

    avatar_repo = AvatarRepository(session)
    avatar = await avatar_repo.get_by_id(avatar_id)

    await state.set_state(DialogState.chatting)
    await state.update_data(avatar_id=avatar_id)

    # Remove keyboard from the original message
    await callback.message.edit_text(
        f"{avatar.emoji} <b>{avatar.name}</b> — выбран!\n\n"
        "<i>Напиши что угодно, чтобы начать общение.</i>"
    )

    # Send avatar greeting in-character with persistent reply keyboard
    greeting = avatar.greeting or _DEFAULT_GREETING
    await callback.message.answer(greeting, reply_markup=main_keyboard())

    await callback.answer()
