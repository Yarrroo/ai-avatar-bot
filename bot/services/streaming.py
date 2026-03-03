import asyncio
import logging
import time

from aiogram import Bot
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramRetryAfter

from bot.services.llm import LLMService
from bot.config import settings
from bot.utils.text import markdown_to_html

logger = logging.getLogger(__name__)

SAFE_LENGTH = 3800  # Buffer for cursor, formatting, and Unicode (Telegram limit is 4096)


def _find_split_point(text: str, limit: int) -> int:
    """Find a good split point near the limit, preferring natural boundaries."""
    pos = text.rfind('\n\n', 0, limit)
    if pos > limit // 2:
        return pos
    pos = text.rfind('\n', 0, limit)
    if pos > limit // 2:
        return pos
    pos = text.rfind('. ', 0, limit)
    if pos > limit // 2:
        return pos + 1
    return limit


async def stream_response_to_telegram(
    bot: Bot,
    chat_id: int,
    llm_service: LLMService,
    messages: list[dict[str, str]],
) -> str:
    """Stream LLM response to Telegram via progressive message edits.

    Handles Telegram's 4096-char limit by splitting into multiple messages.
    Returns the complete response text.
    """
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    sent_message = await bot.send_message(chat_id=chat_id, text="\u258c")

    accumulated = ""
    msg_offset = 0  # Character offset where current message starts
    last_edit_time = 0.0
    last_edit_text = ""

    min_interval = settings.stream_edit_interval
    min_chunk = settings.stream_min_chunk_length

    async def safe_edit(text: str, cursor: bool = True) -> None:
        """Edit current message with retry on rate limit."""
        nonlocal last_edit_time, last_edit_text
        if text == last_edit_text and cursor:
            return
        display = text + " \u258c" if cursor else text
        try:
            await sent_message.edit_text(text=display)
            last_edit_time = time.monotonic()
            last_edit_text = text
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await sent_message.edit_text(text=display)
                last_edit_time = time.monotonic()
                last_edit_text = text
            except Exception:
                pass
        except Exception as e:
            logger.warning("Edit failed: %s", e)

    async def split_to_new_message() -> None:
        """Finalize current message and start a new one for overflow."""
        nonlocal sent_message, msg_offset, last_edit_text, last_edit_time
        current = accumulated[msg_offset:]
        split_at = _find_split_point(current, SAFE_LENGTH)
        final = current[:split_at].rstrip()

        try:
            await sent_message.edit_text(text=final)
        except Exception:
            pass

        msg_offset += split_at
        remainder = accumulated[msg_offset:].lstrip('\n')
        msg_offset = len(accumulated) - len(remainder)

        last_edit_text = ""
        last_edit_time = 0.0
        try:
            sent_message = await bot.send_message(
                chat_id=chat_id,
                text=(remainder + " \u258c") if remainder else "\u258c",
            )
            last_edit_text = remainder
            last_edit_time = time.monotonic()
        except Exception as exc:
            logger.warning("Continuation message failed: %s", exc)

    # Stream from LLM
    try:
        async for chunk in llm_service.chat_stream(messages):
            accumulated += chunk
            current = accumulated[msg_offset:]

            if len(current) > SAFE_LENGTH:
                await split_to_new_message()
                continue

            now = time.monotonic()
            should_edit = (
                len(current) - len(last_edit_text) >= min_chunk
                and (now - last_edit_time) >= min_interval
            )
            if should_edit:
                await safe_edit(current)

    except Exception as e:
        logger.exception("LLM streaming error: %s", e)
        current = accumulated[msg_offset:]
        notice = "\n\n\u26a0\ufe0f Ответ был прерван. Попробуй ещё раз."
        if current:
            error_text = current + notice
            if len(error_text) > SAFE_LENGTH:
                error_text = current[:SAFE_LENGTH - len(notice)] + notice
            await safe_edit(error_text, cursor=False)
        else:
            await safe_edit(
                "\u26a0\ufe0f Не удалось получить ответ. Попробуй ещё раз.",
                cursor=False,
            )
        return accumulated

    # Final edit — remove cursor, apply formatting
    current = accumulated[msg_offset:]
    if current:
        try:
            await sent_message.edit_text(
                text=markdown_to_html(current),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await safe_edit(current, cursor=False)
    else:
        await safe_edit(
            "\u26a0\ufe0f Не удалось получить ответ. Попробуй ещё раз.",
            cursor=False,
        )

    return accumulated
