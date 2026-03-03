from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

# Button labels — also used as text filters in handlers
BTN_CHANGE_AVATAR = "\U0001f504 Персонаж"
BTN_MEMORY = "\U0001f9e0 Память"
BTN_MENU = "\U0001f4cb Меню"

ALL_BUTTON_TEXTS = {BTN_CHANGE_AVATAR, BTN_MEMORY, BTN_MENU}


def main_keyboard() -> ReplyKeyboardMarkup:
    """Persistent reply keyboard shown after avatar selection."""
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text=BTN_CHANGE_AVATAR),
            KeyboardButton(text=BTN_MEMORY),
            KeyboardButton(text=BTN_MENU),
        ]],
        resize_keyboard=True,
        is_persistent=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    """Remove reply keyboard (used during avatar selection)."""
    return ReplyKeyboardRemove()
