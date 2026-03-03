import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import settings
from bot.database.engine import async_session, engine
from bot.database.models import Base
from bot.database.seed import seed_avatars
from bot.handlers.chat import router as chat_router
from bot.handlers.commands import router as commands_router
from bot.handlers.errors import router as errors_router
from bot.handlers.start import router as start_router
from bot.middlewares.db import DbSessionMiddleware
from bot.services.llm import LLMService

logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    """Run startup tasks: create tables, seed data, register commands, set profile."""
    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed avatar data
    async with async_session() as session:
        await seed_avatars(session)
        await session.commit()

    # Register bot commands for Telegram menu
    commands = [
        BotCommand(command="start", description="\U0001f680 Начать / выбрать аватара"),
        BotCommand(command="change_avatar", description="\U0001f504 Сменить аватара"),
        BotCommand(command="history", description="\U0001f4ac История диалога"),
        BotCommand(command="facts", description="\U0001f9e0 Что я о тебе помню"),
        BotCommand(command="reset", description="\U0001f5d1 Очистить историю"),
        BotCommand(command="help", description="\u2753 Помощь"),
    ]
    await bot.set_my_commands(commands)

    logger.info("Bot startup complete: tables created, avatars seeded, commands registered")


async def main() -> None:
    """Initialize and start the bot."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())

    # Register outer middleware: one DB session per update
    dp.update.outer_middleware(DbSessionMiddleware(session_pool=async_session))

    # Inject shared services via dispatcher kwargs
    dp["llm_service"] = LLMService(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        model=settings.llm_model,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
        default_max_tokens=settings.llm_max_tokens,
        default_temperature=settings.llm_temperature,
    )
    dp["session_factory"] = async_session

    # Register startup hook
    dp.startup.register(on_startup)

    # Include routers (order matters: errors first, chat last as catch-all)
    dp.include_routers(
        errors_router,
        start_router,
        commands_router,
        chat_router,
    )

    logger.info("Starting bot polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
