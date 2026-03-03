from aiogram.fsm.state import State, StatesGroup


class DialogState(StatesGroup):
    choosing_avatar = State()
    chatting = State()
