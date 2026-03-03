from bot.handlers.chat import router as chat_router
from bot.handlers.commands import router as commands_router
from bot.handlers.errors import router as errors_router
from bot.handlers.start import router as start_router

__all__ = [
    "errors_router",
    "start_router",
    "commands_router",
    "chat_router",
]
