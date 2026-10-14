from aiogram.fsm.state import State, StatesGroup


class AddBirthday(StatesGroup):
    photo = State()
    name = State()
    birth_date = State()
    position = State()
    branch = State()


class EditBirthday(StatesGroup):
    value = State()


class AddBranch(StatesGroup):
    name = State()


class SettingValue(StatesGroup):
    channel = State()
    template = State()
    caption = State()
    publish_time = State()

