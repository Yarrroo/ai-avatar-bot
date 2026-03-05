from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

if TYPE_CHECKING:
    from bot.database.models import Avatar, MemoryFact


def avatar_selection_keyboard(avatars: list[Avatar]) -> InlineKeyboardMarkup:
    """Build column-layout keyboard for avatar selection.

    Short button labels: "{emoji} {name}".
    callback_data format: "select_avatar:{avatar_id}"
    """
    buttons = []
    for avatar in avatars:
        buttons.append(
            [InlineKeyboardButton(
                text=f"{avatar.emoji} {avatar.name}",
                callback_data=f"select_avatar:{avatar.id}",
            )]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def reset_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Build row-layout keyboard for reset confirmation."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="\u2705 Да", callback_data="reset_confirm"),
                InlineKeyboardButton(text="\u274c Нет", callback_data="reset_cancel"),
            ]
        ]
    )


def fact_deletion_keyboard(
    facts: list[MemoryFact],
    page: int = 0,
    total: int = 0,
    per_page: int = 10,
) -> InlineKeyboardMarkup:
    """Build keyboard with delete buttons for each fact + pagination."""
    buttons = []
    start_num = page * per_page + 1
    for i, fact in enumerate(facts, start_num):
        buttons.append([
            InlineKeyboardButton(
                text=f"\u274c {i}",
                callback_data=f"delete_fact:{fact.id}",
            )
        ])

    # Pagination row
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="\u25c0\ufe0f", callback_data=f"facts_page:{page - 1}",
            ))
        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}", callback_data="noop",
        ))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="\u25b6\ufe0f", callback_data=f"facts_page:{page + 1}",
            ))
        buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def menu_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard shown when user taps the Menu reply button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\U0001f4dc История", callback_data="menu:history",
                ),
                InlineKeyboardButton(
                    text="\U0001f5d1 Сброс", callback_data="menu:reset",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\u2753 Помощь", callback_data="menu:help",
                ),
            ],
        ]
    )
