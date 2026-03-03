import re
from typing import Any


def format_history(messages: list[Any], avatar: Any) -> str:
    """Format message list as HTML conversation history.

    Args:
        messages: List of DialogMessage objects (ordered oldest-first).
        avatar: Avatar object with .emoji and .name attributes.

    Returns:
        Formatted HTML string for Telegram, or empty-state message.
    """
    if not messages:
        return "\U0001f4ac История пуста — напиши что-нибудь, чтобы начать!"

    count = len(messages)
    lines = [f"\U0001f4ac <b>Последние {count} сообщений:</b>\n"]
    for msg in messages:
        content = escape_html(msg.content)
        if len(content) > 300:
            content = content[:297] + "…"
        if msg.role == "user":
            lines.append(f"👤 <b>Вы:</b> {content}")
        else:
            lines.append(f"{avatar.emoji} <b>{avatar.name}:</b> {content}")
    result = "\n\n".join(lines)
    return truncate_text(result, max_length=4000)


def truncate_text(text: str, max_length: int = 4000) -> str:
    """Truncate text to fit Telegram message limits.

    Leaves room for a truncation notice if text exceeds max_length.
    """
    if len(text) <= max_length:
        return text
    suffix = "\n\n<i>…сообщение сокращено</i>"
    return text[: max_length - len(suffix)] + suffix


def escape_html(text: str) -> str:
    """Escape HTML special characters for safe Telegram display."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def markdown_to_html(text: str) -> str:
    """Convert basic Markdown formatting to Telegram HTML.

    Handles **bold**, *italic*, `code` and escapes HTML entities.
    Best-effort — if the result is invalid HTML, caller should fall back
    to plain text.
    """
    text = escape_html(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\w)\*([^\*\n]+?)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'`([^`\n]+?)`', r'<code>\1</code>', text)
    return text
