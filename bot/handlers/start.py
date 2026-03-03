import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repositories import AvatarRepository, UserRepository
from bot.keyboards.inline import avatar_selection_keyboard
from bot.states.dialog import DialogState

logger = logging.getLogger(__name__)

router = Router(name="start")

# Avatar greetings keyed by avatar id -- sent in-character after selection.
AVATAR_GREETINGS: dict[int, str] = {
    1: (
        "<i>*поправляет очки и спрыгивает с книжной полки*</i>\n\n"
        "Мур-р-р, наконец-то достойный собеседник! Я — Учёный кот, "
        "профессор всего на свете.\n\n"
        "Могу объяснить квантовую физику, разобрать теорему Ферма или "
        "просто поболтать о смысле бытия. Правда, 10% моего внимания "
        "всегда занимает солнечный зайчик на стене.\n\n"
        "О чём поговорим?"
    ),
    2: (
        "Йо 👋\n\n"
        "Ладно, я Макс. Мне 17, и я знаю про этот мир больше, чем хотелось бы. "
        "Могу помочь с чем угодно — от домашки по физике до экзистенциального кризиса.\n\n"
        "Только давай без банальностей, ок? Спрашивай что-нибудь интересное."
    ),
    3: (
        "Здравствуй.\n\n"
        "Присядь, огонь в очаге ещё тёплый, а чай настоялся как раз к твоему приходу. "
        "Каждая встреча — это дар, и я рад, что наши дороги пересеклись.\n\n"
        "Расскажи, что у тебя на душе. Я слушаю."
    ),
}


def _build_welcome_text(avatars: list) -> str:
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

    # Send avatar greeting in-character
    greeting = AVATAR_GREETINGS.get(avatar_id, f"Привет! Я — {avatar.name}. Давай пообщаемся!")
    await callback.message.answer(greeting)

    await callback.answer()
