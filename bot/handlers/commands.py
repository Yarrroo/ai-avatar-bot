import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repositories import (
    AvatarRepository,
    FactRepository,
    MessageRepository,
)
from bot.keyboards.inline import avatar_selection_keyboard, reset_confirmation_keyboard
from bot.states.dialog import DialogState
from bot.utils.text import escape_html, format_history, truncate_text

logger = logging.getLogger(__name__)

router = Router(name="commands")


@router.message(Command("history"))
async def cmd_history(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Show last 10 messages from current dialog."""
    data = await state.get_data()
    avatar_id = data.get("avatar_id")
    if not avatar_id:
        await message.answer("Сначала выбери персонажа \U0001f447 /start")
        return

    msg_repo = MessageRepository(session)
    avatar_repo = AvatarRepository(session)

    messages = await msg_repo.get_recent_messages(
        user_id=message.from_user.id,
        avatar_id=avatar_id,
        limit=10,
    )
    avatar = await avatar_repo.get_by_id(avatar_id)

    text = format_history(messages, avatar)
    await message.answer(text)


@router.message(Command("facts"))
async def cmd_facts(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Show all long-term facts remembered about this user+avatar pair."""
    data = await state.get_data()
    avatar_id = data.get("avatar_id")
    if not avatar_id:
        await message.answer("Сначала выбери персонажа \U0001f447 /start")
        return

    fact_repo = FactRepository(session)
    facts = await fact_repo.get_facts(
        user_id=message.from_user.id,
        avatar_id=avatar_id,
    )

    if facts:
        fact_lines = "\n".join(
            f"  \u2022 {escape_html(f.fact_text)}" for f in facts
        )
        text = (
            f"\U0001f9e0 <b>Что я о тебе помню</b> ({len(facts)}):\n\n"
            f"{fact_lines}"
        )
    else:
        text = (
            "\U0001f9e0 Пока ничего не запомнил.\n"
            "Расскажи о себе — и я обязательно что-нибудь запомню!"
        )

    await message.answer(truncate_text(text))


@router.message(Command("reset"))
async def cmd_reset(
    message: Message,
    state: FSMContext,
) -> None:
    """Send reset confirmation prompt with inline keyboard."""
    data = await state.get_data()
    avatar_id = data.get("avatar_id")
    if not avatar_id:
        await message.answer("Сначала выбери персонажа \U0001f447 /start")
        return

    await message.answer(
        "\U0001f5d1 <b>Очистить историю диалога?</b>\n\n"
        "<i>Запомненные факты о тебе сохранятся.</i>",
        reply_markup=reset_confirmation_keyboard(),
    )


@router.callback_query(F.data == "reset_confirm")
async def reset_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Clear dialog history on confirmation."""
    data = await state.get_data()
    avatar_id = data.get("avatar_id")

    if avatar_id:
        msg_repo = MessageRepository(session)
        await msg_repo.clear_history(
            user_id=callback.from_user.id,
            avatar_id=avatar_id,
        )

    await callback.message.edit_text("\u2705 История очищена. Начинаем с чистого листа!")
    await callback.answer()


@router.callback_query(F.data == "reset_cancel")
async def reset_cancel(callback: CallbackQuery) -> None:
    """Cancel reset operation."""
    await callback.message.edit_text("\u21a9\ufe0f Отменено.")
    await callback.answer()


@router.message(Command("change_avatar"))
async def cmd_change_avatar(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Return to avatar selection."""
    data = await state.get_data()
    avatar_id = data.get("avatar_id")

    avatar_repo = AvatarRepository(session)
    avatars = await avatar_repo.get_all()

    avatar_lines = "\n".join(
        f"  {a.emoji} <b>{a.name}</b> — {a.description}" for a in avatars
    )

    header = f"{avatar_lines}\n\n\U0001f447 <b>Выбери аватара:</b>"
    if avatar_id:
        avatar = await avatar_repo.get_by_id(avatar_id)
        if avatar:
            header = (
                f"\U0001f504 Сейчас: {avatar.emoji} <b>{avatar.name}</b>\n\n"
                f"{avatar_lines}\n\n"
                "\U0001f447 <b>Выбери нового:</b>"
            )

    await state.set_state(DialogState.choosing_avatar)
    await message.answer(
        header,
        reply_markup=avatar_selection_keyboard(avatars),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Show available commands."""
    await message.answer(
        "\u2753 <b>Команды</b>\n\n"
        "/start — начать и выбрать аватара\n"
        "/change_avatar — сменить персонажа\n"
        "/history — последние сообщения\n"
        "/facts — что я о тебе помню\n"
        "/reset — очистить историю\n"
        "/help — эта справка\n\n"
        "<i>\U0001f4a1 Факты сохраняются даже после сброса истории.</i>"
    )
