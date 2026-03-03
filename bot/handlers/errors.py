import logging

from aiogram import Router
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)

router = Router(name="errors")


@router.errors()
async def global_error_handler(event: ErrorEvent) -> bool:
    """Handle all unhandled exceptions globally."""
    logger.exception(
        "Unhandled exception in update %s: %s",
        event.update.update_id,
        event.exception,
    )

    # Attempt to notify the user
    update = event.update
    chat_id = None
    if update.message:
        chat_id = update.message.chat.id
    elif update.callback_query and update.callback_query.message:
        chat_id = update.callback_query.message.chat.id

    if chat_id:
        try:
            await event.update.bot.send_message(
                chat_id,
                "\u26a0\ufe0f Что-то пошло не так. Попробуй ещё раз.",
            )
        except Exception:
            pass  # If even error notification fails, just log

    return True  # Prevent further propagation
