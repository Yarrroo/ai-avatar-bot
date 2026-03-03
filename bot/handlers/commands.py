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
from bot.keyboards.inline import (
    avatar_selection_keyboard,
    fact_deletion_keyboard,
    menu_inline_keyboard,
    reset_confirmation_keyboard,
)
from bot.keyboards.reply import BTN_CHANGE_AVATAR, BTN_MEMORY, BTN_MENU
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
    """Show long-term facts with pagination."""
    data = await state.get_data()
    avatar_id = data.get("avatar_id")
    if not avatar_id:
        await message.answer("Сначала выбери персонажа \U0001f447 /start")
        return

    await _send_facts_page(message, session, message.from_user.id, avatar_id, page=0)


async def _send_facts_page(
    target: Message,
    session: AsyncSession,
    user_id: int,
    avatar_id: int,
    page: int = 0,
    edit: bool = False,
) -> None:
    """Build and send/edit a paginated facts message."""
    from bot.database.repositories.fact import FACTS_PER_PAGE

    fact_repo = FactRepository(session)
    facts, total = await fact_repo.get_facts_page(
        user_id=user_id,
        avatar_id=avatar_id,
        page=page,
    )

    if not facts and page == 0:
        text = (
            "\U0001f9e0 Пока ничего не запомнил.\n"
            "Расскажи о себе — и я обязательно что-нибудь запомню!"
        )
        if edit:
            await target.edit_text(text)
        else:
            await target.answer(text)
        return

    start_num = page * FACTS_PER_PAGE + 1
    fact_lines = "\n".join(
        f"  {i}. {escape_html(f.fact_text)}" for i, f in enumerate(facts, start_num)
    )
    text = (
        f"\U0001f9e0 <b>Что я о тебе помню</b> ({total}):\n\n"
        f"{fact_lines}\n\n"
        "<i>Нажми \u274c чтобы удалить неверный факт.</i>"
    )
    markup = fact_deletion_keyboard(facts, page=page, total=total, per_page=FACTS_PER_PAGE)

    if edit:
        await target.edit_text(truncate_text(text), reply_markup=markup)
    else:
        await target.answer(truncate_text(text), reply_markup=markup)


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


@router.callback_query(F.data.startswith("delete_fact:"))
async def delete_fact(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Soft-delete a single long-term fact."""
    fact_id = int(callback.data.split(":")[1])
    fact_repo = FactRepository(session)
    deleted = await fact_repo.deactivate_fact(
        fact_id=fact_id,
        user_id=callback.from_user.id,
    )

    if deleted:
        await callback.answer("\u2705 Факт удалён")
        # Refresh the facts page in-place
        data = await state.get_data()
        avatar_id = data.get("avatar_id")
        if avatar_id:
            await _send_facts_page(
                callback.message, session,
                callback.from_user.id, avatar_id,
                page=0, edit=True,
            )
        else:
            await callback.message.edit_reply_markup(reply_markup=None)
    else:
        await callback.answer("\u26a0\ufe0f Факт не найден", show_alert=True)


@router.callback_query(F.data.startswith("facts_page:"))
async def facts_page(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Handle facts pagination."""
    page = int(callback.data.split(":")[1])
    data = await state.get_data()
    avatar_id = data.get("avatar_id")
    if not avatar_id:
        await callback.answer()
        return

    await callback.answer()
    await _send_facts_page(
        callback.message, session,
        callback.from_user.id, avatar_id,
        page=page, edit=True,
    )


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    """Ignore clicks on pagination counter."""
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


# ── Reply-keyboard button handlers ──────────────────────────────────


@router.message(DialogState.chatting, F.text == BTN_CHANGE_AVATAR)
async def btn_change_avatar(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Handle '🔄 Персонаж' reply-keyboard button."""
    await cmd_change_avatar(message, state, session)


@router.message(DialogState.chatting, F.text == BTN_MEMORY)
async def btn_memory(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Handle '🧠 Память' reply-keyboard button."""
    await cmd_facts(message, state, session)


@router.message(DialogState.chatting, F.text == BTN_MENU)
async def btn_menu(message: Message) -> None:
    """Handle '📋 Меню' reply-keyboard button — show inline menu."""
    await message.answer(
        "\U0001f4cb <b>Меню</b>",
        reply_markup=menu_inline_keyboard(),
    )


# ── Inline-menu callback handlers ───────────────────────────────────


@router.callback_query(F.data == "menu:history")
async def menu_history(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Handle inline menu → История."""
    await callback.answer()
    data = await state.get_data()
    avatar_id = data.get("avatar_id")
    if not avatar_id:
        await callback.message.answer("Сначала выбери персонажа \U0001f447 /start")
        return

    msg_repo = MessageRepository(session)
    avatar_repo = AvatarRepository(session)
    messages = await msg_repo.get_recent_messages(
        user_id=callback.from_user.id,
        avatar_id=avatar_id,
        limit=10,
    )
    avatar = await avatar_repo.get_by_id(avatar_id)
    text = format_history(messages, avatar)
    await callback.message.answer(text)


@router.callback_query(F.data == "menu:reset")
async def menu_reset(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """Handle inline menu → Сброс."""
    await callback.answer()
    data = await state.get_data()
    avatar_id = data.get("avatar_id")
    if not avatar_id:
        await callback.message.answer("Сначала выбери персонажа \U0001f447 /start")
        return

    await callback.message.answer(
        "\U0001f5d1 <b>Очистить историю диалога?</b>\n\n"
        "<i>Запомненные факты о тебе сохранятся.</i>",
        reply_markup=reset_confirmation_keyboard(),
    )


@router.callback_query(F.data == "menu:help")
async def menu_help(callback: CallbackQuery) -> None:
    """Handle inline menu → Помощь."""
    await callback.answer()
    await callback.message.answer(
        "\u2753 <b>Команды</b>\n\n"
        "/start — начать и выбрать аватара\n"
        "/change_avatar — сменить персонажа\n"
        "/history — последние сообщения\n"
        "/facts — что я о тебе помню\n"
        "/reset — очистить историю\n"
        "/help — эта справка\n\n"
        "<i>\U0001f4a1 Факты сохраняются даже после сброса истории.</i>"
    )
