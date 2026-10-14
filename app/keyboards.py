from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить именинника", callback_data="menu:add")
    builder.button(text="🎂 Именинники", callback_data="menu:birthdays")
    builder.button(text="🏢 Филиалы", callback_data="menu:branches")
    builder.button(text="⚙️ Настройки", callback_data="menu:settings")
    builder.adjust(1, 1, 2)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel")]]
    )


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:main")]]
    )


def branch_picker(branches: list[dict[str, Any]], prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for branch in branches:
        builder.button(text=f"🏢 {branch['name']}", callback_data=f"{prefix}:{branch['id']}")
    builder.button(text="✖️ Отмена", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def birthdays_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Текущий месяц", callback_data="month:0")
    builder.button(text="🗓 Следующий месяц", callback_data="month:1")
    builder.button(text="🔎 Найти / редактировать", callback_data="birthdays:all")
    builder.button(text="⬅️ Назад", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def birthdays_list(rows: list[dict[str, Any]], offset: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for row in rows:
        day = int(str(row["birth_date"])[8:10])
        builder.button(text=f"{day:02d} · {row['name']}", callback_data=f"birthday:view:{row['id']}")
    builder.button(text="⬅️ К разделу", callback_data="menu:birthdays")
    builder.adjust(1)
    return builder.as_markup()


def birthday_card(birthday_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редактировать", callback_data=f"birthday:edit:{birthday_id}")
    builder.button(text="🗑 Удалить", callback_data=f"birthday:delete:{birthday_id}")
    builder.button(text="⬅️ К спискам", callback_data="menu:birthdays")
    builder.adjust(2, 1)
    return builder.as_markup()


def edit_birthday_menu(birthday_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    fields = [
        ("📷 Фото", "photo"),
        ("👤 Имя", "name"),
        ("📅 Дата", "birth_date"),
        ("💼 Должность", "position"),
        ("🏢 Филиал", "branch"),
    ]
    for label, field in fields:
        builder.button(text=label, callback_data=f"birthday:field:{birthday_id}:{field}")
    builder.button(text="⬅️ Назад", callback_data=f"birthday:view:{birthday_id}")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def delete_confirmation(birthday_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, удалить", callback_data=f"birthday:confirm_delete:{birthday_id}")
    builder.button(text="Нет", callback_data=f"birthday:view:{birthday_id}")
    builder.adjust(2)
    return builder.as_markup()


def branches_menu(branches: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить филиал", callback_data="branch:add")
    for branch in branches:
        builder.button(
            text=f"🗑 {branch['name']} ({branch['birthday_count']})",
            callback_data=f"branch:delete:{branch['id']}",
        )
    builder.button(text="⬅️ Назад", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def settings_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📣 Канал публикации", callback_data="settings:channel")
    builder.button(text="🖼 PNG-шаблон", callback_data="settings:template")
    builder.button(text="📝 Текст поздравления", callback_data="settings:caption")
    builder.button(text="⏰ Время публикации", callback_data="settings:time")
    builder.button(text="⬅️ Назад", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()
