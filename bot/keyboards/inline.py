from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def avatar_selection_keyboard(avatars: list) -> InlineKeyboardMarkup:
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
