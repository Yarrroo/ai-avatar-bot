import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.services.llm import LLMService
from bot.services.memory import MemoryService
from bot.services.streaming import stream_response_to_telegram
from bot.states.dialog import DialogState

logger = logging.getLogger(__name__)

router = Router(name="chat")


@router.message(DialogState.chatting, F.text)
async def handle_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    llm_service: LLMService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Process user message: build context, call LLM, stream response, save both."""
    data = await state.get_data()
    avatar_id = data["avatar_id"]
    memory = MemoryService(session)

    try:
        # 1. Save user message FIRST so concurrent requests see it
        await memory.save_message(
            user_id=message.from_user.id,
            avatar_id=avatar_id,
            role="user",
            content=message.text,
        )

        # 2. Build prompt: system prompt + facts + recent history
        #    (current message is already in DB from step 1)
        prompt_messages = await memory.build_prompt(
            user_id=message.from_user.id,
            avatar_id=avatar_id,
        )

        # 3. Stream LLM response to Telegram
        full_response = await stream_response_to_telegram(
            bot=message.bot,
            chat_id=message.chat.id,
            llm_service=llm_service,
            messages=prompt_messages,
        )

        # 4. Save assistant response to DB
        if full_response:
            await memory.save_message(
                user_id=message.from_user.id,
                avatar_id=avatar_id,
                role="assistant",
                content=full_response,
            )

        # 5. Trigger fact extraction if interval reached (background task)
        await memory.maybe_extract_facts(
            user_id=message.from_user.id,
            avatar_id=avatar_id,
            llm=llm_service,
            session_factory=session_factory,
        )

    except Exception:
        logger.exception("Error handling message from user %s", message.from_user.id)
        await message.answer(
            "\u26a0\ufe0f Что-то пошло не так. Попробуй ещё раз."
        )


@router.message(DialogState.chatting, ~F.text)
async def handle_non_text(message: Message) -> None:
    """Inform user that only text messages are supported."""
    await message.answer("Я пока понимаю только текст \U0001f4dd")


@router.message()
async def handle_no_avatar(message: Message) -> None:
    """Catch messages when no avatar is selected."""
    await message.answer("Привет! Выбери персонажа, чтобы начать \U0001f447 /start")
