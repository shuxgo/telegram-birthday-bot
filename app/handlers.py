from __future__ import annotations

import html
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message, MessageOriginChannel, MessageOriginUser

from .config import Config
from .database import Database
from .image_service import render_card, validate_overlay
from .keyboards import (
    back_to_menu,
    birthday_card,
    birthdays_list,
    birthdays_menu,
    branch_picker,
    branches_menu,
    cancel_keyboard,
    delete_confirmation,
    edit_birthday_menu,
    main_menu,
    moderators_menu,
    settings_menu,
)
from .states import AddBirthday, AddBranch, AddModerator, EditBirthday, SettingValue
from .utils import (
    MONTHS_RU,
    display_birth_date,
    month_bounds,
    parse_birth_date,
    parse_publish_time,
    render_caption,
    validate_caption_template,
    validate_group_caption_template,
)


logger = logging.getLogger(__name__)
router = Router(name="admin")


async def _show_main(target: Message, is_owner: bool) -> None:
    role = "главный администратор" if is_owner else "модератор"
    await target.answer(
        "🎉 <b>Бот поздравлений</b>\n\n"
        f"Роль: <b>{role}</b>. Добавляйте именинников, управляйте филиалами и настройками публикации.",
        reply_markup=main_menu(is_owner),
    )


async def _show_birthday(message: Message, birthday_id: int, db: Database, config: Config) -> None:
    row = await db.get_birthday(birthday_id)
    if not row:
        await message.answer("Запись не найдена.", reply_markup=birthdays_menu())
        return
    settings = await db.get_settings()
    preview_path = config.data_dir / "cards" / f"preview-{birthday_id}.jpg"
    caption = render_caption(settings["caption_template"], row)
    try:
        render_card(Path(row["photo_path"]), Path(settings["template_path"]), preview_path)
        await message.answer_photo(
            FSInputFile(preview_path),
            caption=caption,
            reply_markup=birthday_card(birthday_id),
        )
    except Exception:
        logger.exception("Could not render preview for birthday %s", birthday_id)
        await message.answer(
            caption + "\n\n⚠️ Не удалось собрать открытку. Проверьте фото и PNG-шаблон.",
            reply_markup=birthday_card(birthday_id),
        )


@router.message(CommandStart())
@router.message(Command("menu"))
async def command_start(message: Message, state: FSMContext, is_owner: bool) -> None:
    await state.clear()
    await _show_main(message, is_owner)


@router.callback_query(F.data == "menu:main")
async def menu_main(callback: CallbackQuery, state: FSMContext, is_owner: bool) -> None:
    await state.clear()
    await callback.answer()
    await _show_main(callback.message, is_owner)


@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext, is_owner: bool) -> None:
    await state.clear()
    await callback.answer("Действие отменено")
    await _show_main(callback.message, is_owner)


# ---- Persistent control panel -------------------------------------------


@router.message(F.text == "🎂 Новый именинник")
async def panel_add_birthday(message: Message, state: FSMContext, db: Database) -> None:
    branches = await db.list_branches()
    if not branches:
        await message.answer("Сначала добавьте хотя бы один филиал.", reply_markup=settings_menu())
        return
    await state.clear()
    await state.set_state(AddBirthday.photo)
    await message.answer(
        "Шаг 1 из 5. Пришлите фотографию именинника.", reply_markup=cancel_keyboard()
    )


@router.message(F.text == "📅 Именинники")
async def panel_birthdays(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🎂 <b>Именинники</b>", reply_markup=birthdays_menu())


@router.message(F.text == "⚙️ Настройки")
async def panel_settings(
    message: Message, state: FSMContext, db: Database, config: Config
) -> None:
    await state.clear()
    await message.answer(await _settings_status(db, config), reply_markup=settings_menu())


@router.message(F.text == "👥 Модераторы")
async def panel_moderators(
    message: Message, state: FSMContext, db: Database, config: Config, is_owner: bool
) -> None:
    await state.clear()
    if not is_owner:
        await message.answer("Только главный администратор может управлять модераторами.")
        return
    await _show_moderators(message, db, config)


# ---- Add birthday wizard -------------------------------------------------


@router.callback_query(F.data == "menu:add")
async def add_birthday_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    branches = await db.list_branches()
    if not branches:
        await callback.answer()
        await callback.message.answer("Сначала добавьте хотя бы один филиал.", reply_markup=back_to_menu())
        return
    await state.clear()
    await state.set_state(AddBirthday.photo)
    await callback.answer()
    await callback.message.answer(
        "Шаг 1 из 5. Пришлите фотографию именинника.", reply_markup=cancel_keyboard()
    )


@router.message(AddBirthday.photo, F.photo)
async def add_birthday_photo(message: Message, state: FSMContext, bot: Bot, config: Config) -> None:
    destination = config.data_dir / "photos" / f"{uuid4().hex}.jpg"
    await bot.download(message.photo[-1], destination=destination)
    await state.update_data(photo_path=str(destination), photo_file_id=message.photo[-1].file_id)
    await state.set_state(AddBirthday.name)
    await message.answer("Шаг 2 из 5. Введите имя и фамилию.", reply_markup=cancel_keyboard())


@router.message(AddBirthday.photo)
async def add_birthday_photo_invalid(message: Message) -> None:
    await message.answer("Нужно прислать фотографию как фото, не как текст.", reply_markup=cancel_keyboard())


@router.message(AddBirthday.name, F.text)
async def add_birthday_name(message: Message, state: FSMContext) -> None:
    value = message.text.strip()
    if not 2 <= len(value) <= 120:
        await message.answer("Имя должно содержать от 2 до 120 символов.")
        return
    await state.update_data(name=value)
    await state.set_state(AddBirthday.birth_date)
    await message.answer(
        "Шаг 3 из 5. Введите дату рождения: <b>ДД.ММ</b> или <b>ДД.ММ.ГГГГ</b>.\n"
        "Год можно не указывать — поздравление всё равно повторяется ежегодно.",
        reply_markup=cancel_keyboard(),
    )


@router.message(AddBirthday.birth_date, F.text)
async def add_birthday_date(message: Message, state: FSMContext) -> None:
    try:
        parsed = parse_birth_date(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(birth_date=parsed.isoformat())
    await state.set_state(AddBirthday.position)
    await message.answer("Шаг 4 из 5. Введите должность или специализацию.", reply_markup=cancel_keyboard())


@router.message(AddBirthday.position, F.text)
async def add_birthday_position(message: Message, state: FSMContext, db: Database) -> None:
    value = message.text.strip()
    if not 2 <= len(value) <= 160:
        await message.answer("Должность должна содержать от 2 до 160 символов.")
        return
    await state.update_data(position=value)
    await state.set_state(AddBirthday.branch)
    branches = await db.list_branches()
    await message.answer(
        "Шаг 5 из 5. Выберите филиал:",
        reply_markup=branch_picker(branches, "addbranch"),
    )


@router.callback_query(AddBirthday.branch, F.data.startswith("addbranch:"))
async def add_birthday_finish(
    callback: CallbackQuery, state: FSMContext, db: Database, config: Config
) -> None:
    branch_id = int(callback.data.rsplit(":", 1)[1])
    data = await state.get_data()
    birthday_id = await db.add_birthday(
        name=data["name"],
        birth_date=data["birth_date"],
        position=data["position"],
        branch_id=branch_id,
        photo_file_id=data["photo_file_id"],
        photo_path=data["photo_path"],
    )
    await state.clear()
    await callback.answer("Именинник сохранён")
    await callback.message.answer("✅ Именинник сохранён. Вот предварительный вид открытки:")
    await _show_birthday(callback.message, birthday_id, db, config)


# ---- Lists and editing ---------------------------------------------------


@router.callback_query(F.data == "menu:birthdays")
async def menu_birthdays(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.answer("🎂 <b>Именинники</b>", reply_markup=birthdays_menu())


@router.callback_query(F.data.startswith("month:"))
async def list_month(callback: CallbackQuery, db: Database, config: Config) -> None:
    offset = int(callback.data.split(":")[1])
    now = datetime.now(config.timezone)
    year, month = month_bounds(now, offset)
    rows = await db.list_birthdays_for_month(year, month)
    lines = [f"📅 <b>Именинники — {MONTHS_RU[month - 1]} {year}</b>"]
    if rows:
        lines.extend(
            f"{display_birth_date(row['birth_date'])} — <b>{html.escape(row['name'])}</b>, "
            f"{html.escape(row['position'])}, {html.escape(row['branch_name'])}"
            for row in rows
        )
    else:
        lines.append("В этом месяце записей нет.")
    await callback.answer()
    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n\n{line}" if current else line
        if len(candidate) > 3500 and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    for index, chunk in enumerate(chunks):
        markup = birthdays_list(rows, offset) if index == len(chunks) - 1 else None
        await callback.message.answer(chunk, reply_markup=markup)


@router.callback_query(F.data == "birthdays:all")
async def list_all(callback: CallbackQuery, db: Database) -> None:
    rows = await db.list_all_birthdays()
    await callback.answer()
    if not rows:
        await callback.message.answer("Именинников пока нет.", reply_markup=birthdays_menu())
        return
    # Telegram callback keyboards have a practical size limit; split large databases.
    for page_number, start in enumerate(range(0, len(rows), 50), start=1):
        page = rows[start:start + 50]
        title = "🔎 <b>Все именинники</b>" if len(rows) <= 50 else f"🔎 <b>Все именинники — страница {page_number}</b>"
        await callback.message.answer(title, reply_markup=birthdays_list(page, 0))


@router.callback_query(F.data.startswith("birthday:view:"))
async def birthday_view(callback: CallbackQuery, db: Database, config: Config) -> None:
    birthday_id = int(callback.data.rsplit(":", 1)[1])
    await callback.answer()
    await _show_birthday(callback.message, birthday_id, db, config)


@router.callback_query(F.data.startswith("birthday:edit:"))
async def birthday_edit_menu(callback: CallbackQuery, db: Database) -> None:
    birthday_id = int(callback.data.rsplit(":", 1)[1])
    row = await db.get_birthday(birthday_id)
    await callback.answer()
    if not row:
        await callback.message.answer("Запись не найдена.")
        return
    await callback.message.answer(
        f"Что изменить у <b>{html.escape(row['name'])}</b>?",
        reply_markup=edit_birthday_menu(birthday_id),
    )


@router.callback_query(F.data.startswith("birthday:field:"))
async def birthday_edit_field(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    _, _, birthday_id_text, field = callback.data.split(":")
    birthday_id = int(birthday_id_text)
    await callback.answer()
    if field == "branch":
        branches = await db.list_branches()
        await callback.message.answer(
            "Выберите новый филиал:",
            reply_markup=branch_picker(branches, f"editbranch:{birthday_id}"),
        )
        return
    prompts = {
        "photo": "Пришлите новое фото.",
        "name": "Введите новое имя и фамилию.",
        "birth_date": "Введите новую дату в формате ДД.ММ или ДД.ММ.ГГГГ.",
        "position": "Введите новую должность или специализацию.",
    }
    if field not in prompts:
        await callback.message.answer("Неизвестное поле.")
        return
    await state.set_state(EditBirthday.value)
    await state.set_data({"birthday_id": birthday_id, "field": field})
    await callback.message.answer(prompts[field], reply_markup=cancel_keyboard())


@router.callback_query(F.data.startswith("editbranch:"))
async def birthday_edit_branch(callback: CallbackQuery, db: Database, config: Config) -> None:
    _, birthday_id_text, branch_id_text = callback.data.split(":")
    birthday_id, branch_id = int(birthday_id_text), int(branch_id_text)
    await db.update_birthday(birthday_id, "branch_id", branch_id)
    await callback.answer("Филиал обновлён")
    await _show_birthday(callback.message, birthday_id, db, config)


@router.message(EditBirthday.value)
async def birthday_edit_value(
    message: Message, state: FSMContext, db: Database, bot: Bot, config: Config
) -> None:
    data = await state.get_data()
    birthday_id, field = int(data["birthday_id"]), data["field"]
    if field == "photo":
        if not message.photo:
            await message.answer("Нужно прислать новое изображение как фото.")
            return
        destination = config.data_dir / "photos" / f"{uuid4().hex}.jpg"
        await bot.download(message.photo[-1], destination=destination)
        await db.update_birthday_photo(birthday_id, message.photo[-1].file_id, str(destination))
    else:
        if not message.text:
            await message.answer("Пришлите значение текстом.")
            return
        value = message.text.strip()
        if field == "birth_date":
            try:
                value = parse_birth_date(value).isoformat()
            except ValueError as exc:
                await message.answer(str(exc))
                return
        elif field == "name" and not 2 <= len(value) <= 120:
            await message.answer("Имя должно содержать от 2 до 120 символов.")
            return
        elif field == "position" and not 2 <= len(value) <= 160:
            await message.answer("Должность должна содержать от 2 до 160 символов.")
            return
        await db.update_birthday(birthday_id, field, value)
    await state.clear()
    await message.answer("✅ Данные обновлены.")
    await _show_birthday(message, birthday_id, db, config)


@router.callback_query(F.data.startswith("birthday:delete:"))
async def birthday_delete_prompt(callback: CallbackQuery, db: Database) -> None:
    birthday_id = int(callback.data.rsplit(":", 1)[1])
    row = await db.get_birthday(birthday_id)
    await callback.answer()
    if not row:
        await callback.message.answer("Запись уже удалена.")
        return
    await callback.message.answer(
        f"Удалить <b>{html.escape(row['name'])}</b>? Это действие нельзя отменить.",
        reply_markup=delete_confirmation(birthday_id),
    )


@router.callback_query(F.data.startswith("birthday:confirm_delete:"))
async def birthday_delete_confirm(callback: CallbackQuery, db: Database) -> None:
    birthday_id = int(callback.data.rsplit(":", 1)[1])
    deleted = await db.delete_birthday(birthday_id)
    await callback.answer("Удалено" if deleted else "Запись не найдена")
    await callback.message.answer("🗑 Запись удалена.", reply_markup=birthdays_menu())


# ---- Branches ------------------------------------------------------------


@router.callback_query(F.data == "menu:branches")
async def menu_branches(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    rows = await db.list_branches()
    await callback.answer()
    await callback.message.answer(
        "🏢 <b>Филиалы</b>\n\nЧисло в скобках — количество активных именинников. "
        "Филиал с именинниками удалить нельзя.",
        reply_markup=branches_menu(rows),
    )


@router.callback_query(F.data == "branch:add")
async def branch_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddBranch.name)
    await callback.answer()
    await callback.message.answer("Введите название нового филиала.", reply_markup=cancel_keyboard())


@router.message(AddBranch.name, F.text)
async def branch_add_finish(message: Message, state: FSMContext, db: Database) -> None:
    name = message.text.strip()
    if not 2 <= len(name) <= 100:
        await message.answer("Название должно содержать от 2 до 100 символов.")
        return
    try:
        await db.add_branch(name)
    except sqlite3.IntegrityError:
        await message.answer("Такой филиал уже существует.")
        return
    await state.clear()
    await message.answer("✅ Филиал добавлен.", reply_markup=branches_menu(await db.list_branches()))


@router.callback_query(F.data.startswith("branch:delete:"))
async def branch_delete(callback: CallbackQuery, db: Database) -> None:
    branch_id = int(callback.data.rsplit(":", 1)[1])
    deleted = await db.delete_branch(branch_id)
    await callback.answer("Филиал удалён" if deleted else "В филиале есть именинники", show_alert=not deleted)
    await callback.message.answer("🏢 Филиалы:", reply_markup=branches_menu(await db.list_branches()))


# ---- Moderators ----------------------------------------------------------


async def _show_moderators(message: Message, db: Database, config: Config) -> None:
    rows = await db.list_moderators()
    lines = []
    for row in rows:
        label = row.get("full_name") or (f"@{row['username']}" if row.get("username") else row["user_id"])
        lines.append(f"• <b>{html.escape(str(label))}</b> — <code>{row['user_id']}</code>")
    owner = next(iter(config.admin_ids))
    await message.answer(
        f"👥 <b>Модераторы</b>\n\nГлавный администратор: <code>{owner}</code>\n\n"
        + ("\n".join(lines) if lines else "Модераторов пока нет."),
        reply_markup=moderators_menu(rows),
    )


@router.callback_query(F.data == "menu:moderators")
async def menu_moderators(
    callback: CallbackQuery, state: FSMContext, db: Database, config: Config, is_owner: bool
) -> None:
    if not is_owner:
        await callback.answer("Только для главного администратора", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    await _show_moderators(callback.message, db, config)


@router.callback_query(F.data == "moderator:add")
async def moderator_add_start(callback: CallbackQuery, state: FSMContext, is_owner: bool) -> None:
    if not is_owner:
        await callback.answer("Только для главного администратора", show_alert=True)
        return
    await state.set_state(AddModerator.user_id)
    await callback.answer()
    await callback.message.answer(
        "Перешлите сообщение будущего модератора или отправьте его числовой Telegram ID.",
        reply_markup=cancel_keyboard(),
    )


@router.message(AddModerator.user_id)
async def moderator_add_finish(
    message: Message, state: FSMContext, db: Database, config: Config, is_owner: bool
) -> None:
    if not is_owner:
        await state.clear()
        await message.answer("Только главный администратор может назначать модераторов.")
        return
    forwarded = message.forward_origin.sender_user if isinstance(message.forward_origin, MessageOriginUser) else None
    raw = (message.text or "").strip()
    user_id = forwarded.id if forwarded else int(raw) if raw.isdigit() else None
    if not user_id:
        await message.answer("Перешлите сообщение пользователя или отправьте его числовой Telegram ID.")
        return
    if user_id in config.admin_ids:
        await message.answer("Этот пользователь уже является главным администратором.")
        return
    await db.add_moderator(
        user_id,
        message.from_user.id,
        username=forwarded.username if forwarded else None,
        full_name=forwarded.full_name if forwarded else None,
    )
    await state.clear()
    await message.answer(f"✅ Пользователь <code>{user_id}</code> назначен модератором.")
    await _show_moderators(message, db, config)


@router.callback_query(F.data.startswith("moderator:remove:"))
async def moderator_remove(
    callback: CallbackQuery, db: Database, config: Config, is_owner: bool
) -> None:
    if not is_owner:
        await callback.answer("Только для главного администратора", show_alert=True)
        return
    user_id = int(callback.data.rsplit(":", 1)[1])
    await db.remove_moderator(user_id)
    await callback.answer("Доступ отозван")
    await _show_moderators(callback.message, db, config)


# ---- Settings ------------------------------------------------------------


async def _settings_status(db: Database, config: Config) -> str:
    settings = await db.get_settings()
    stats = await db.publication_stats(datetime.now(config.timezone).year)
    channel = settings.get("channel_title") or settings.get("channel_id") or "не настроен"
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"📣 Канал: <b>{html.escape(channel)}</b>\n"
        f"⏰ Публикация: <b>{settings.get('publish_time', '09:00')}</b> "
        f"({html.escape(str(config.timezone))})\n"
        f"🖼 Шаблон: <b>{html.escape(Path(settings['template_path']).name)}</b>\n\n"
        f"За {datetime.now(config.timezone).year} год: опубликовано {stats['published']}, "
        f"ошибок {stats['failed']}."
    )


@router.callback_query(F.data == "menu:settings")
async def menu_settings(callback: CallbackQuery, state: FSMContext, db: Database, config: Config) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.answer(await _settings_status(db, config), reply_markup=settings_menu())


@router.callback_query(F.data == "settings:channel")
async def settings_channel_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingValue.channel)
    await callback.answer()
    await callback.message.answer(
        "Перешлите сюда любое сообщение из нужного канала или отправьте его "
        "<b>@username</b> / числовой ID вида <code>-100…</code>.\n\n"
        "Бот должен быть администратором канала с правом публикации.",
        reply_markup=cancel_keyboard(),
    )


@router.message(SettingValue.channel)
async def settings_channel_finish(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    channel: int | str | None = None
    if isinstance(message.forward_origin, MessageOriginChannel):
        channel = message.forward_origin.chat.id
    elif message.text:
        raw = message.text.strip()
        if raw.startswith("@") and len(raw) > 1:
            channel = raw
        elif raw.lstrip("-").isdigit():
            channel = int(raw)
    if channel is None:
        await message.answer("Не удалось определить канал. Перешлите пост или укажите @username / -100…")
        return
    try:
        chat = await bot.get_chat(channel)
        if chat.type != ChatType.CHANNEL:
            await message.answer("Указанный чат не является каналом.")
            return
        me = await bot.get_me()
        member = await bot.get_chat_member(chat.id, me.id)
        if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
            await message.answer("Бот найден в канале, но не является его администратором.")
            return
        if (
            member.status == ChatMemberStatus.ADMINISTRATOR
            and not getattr(member, "can_post_messages", False)
        ):
            await message.answer("У бота нет права публиковать сообщения в этом канале.")
            return
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        await message.answer(f"Не удалось проверить канал: {html.escape(str(exc))}")
        return
    title = chat.title or chat.username or str(chat.id)
    await db.set_setting("channel_id", str(chat.id))
    await db.set_setting("channel_title", title)
    await state.clear()
    await message.answer(f"✅ Канал «<b>{html.escape(title)}</b>» сохранён.", reply_markup=settings_menu())


@router.callback_query(F.data == "settings:template")
async def settings_template_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingValue.template)
    await callback.answer()
    await callback.message.answer(
        "Пришлите дизайн <b>как документ PNG</b>, чтобы Telegram не удалил прозрачность.\n\n"
        "Прозрачная область станет вырезом для фотографии. Рекомендуемый размер — 1080×1080.",
        reply_markup=cancel_keyboard(),
    )


@router.message(SettingValue.template, F.document)
async def settings_template_finish(
    message: Message, state: FSMContext, db: Database, bot: Bot, config: Config
) -> None:
    filename = (message.document.file_name or "").lower()
    if not filename.endswith(".png"):
        await message.answer("Нужен именно PNG-файл, отправленный как документ.")
        return
    destination = config.data_dir / "templates" / f"template-{uuid4().hex}.png"
    await bot.download(message.document, destination=destination)
    try:
        width, height = validate_overlay(destination)
    except ValueError as exc:
        destination.unlink(missing_ok=True)
        await message.answer(f"Шаблон не принят: {html.escape(str(exc))}")
        return
    await db.set_setting("template_path", str(destination))
    await state.clear()
    await message.answer(
        f"✅ Шаблон {width}×{height} сохранён. Он будет применяться ко всем будущим публикациям.",
        reply_markup=settings_menu(),
    )


@router.message(SettingValue.template)
async def settings_template_invalid(message: Message) -> None:
    await message.answer("Отправьте PNG именно как файл/документ, а не как сжатую фотографию.")


@router.callback_query(F.data == "settings:caption")
async def settings_caption_start(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    current = await db.get_setting("caption_template", "")
    await state.set_state(SettingValue.caption)
    await callback.answer()
    await callback.message.answer(
        "Отправьте новый текст поздравления. Доступны переменные: "
        "<code>{name}</code>, <code>{position}</code>, <code>{branch}</code>, <code>{date}</code>.\n\n"
        f"<b>Текущий шаблон:</b>\n{html.escape(current)}",
        reply_markup=cancel_keyboard(),
    )


@router.message(SettingValue.caption, F.text)
async def settings_caption_finish(message: Message, state: FSMContext, db: Database) -> None:
    try:
        validate_caption_template(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    sample = {
        "name": "Анна Иванова",
        "position": "специалист",
        "branch_name": "Главный филиал",
        "birth_date": "2000-01-01",
    }
    try:
        await message.answer("<b>Предпросмотр:</b>\n" + render_caption(message.text, sample))
    except TelegramBadRequest as exc:
        await message.answer(
            "Telegram не принимает разметку этого текста. Проверьте HTML-теги: "
            f"{html.escape(str(exc))}"
        )
        return
    await db.set_setting("caption_template", message.text)
    await state.clear()
    await message.answer("✅ Текст поздравления сохранён.", reply_markup=settings_menu())


@router.callback_query(F.data == "settings:group_caption")
async def settings_group_caption_start(
    callback: CallbackQuery, state: FSMContext, db: Database
) -> None:
    current = await db.get_setting("group_caption_template", "")
    await state.set_state(SettingValue.group_caption)
    await callback.answer()
    await callback.message.answer(
        "Отправьте общий текст для 2–9 именинников. Обязательная переменная: "
        "<code>{people}</code>; также доступна <code>{count}</code>.\n\n"
        f"<b>Текущий шаблон:</b>\n{html.escape(current)}",
        reply_markup=cancel_keyboard(),
    )


@router.message(SettingValue.group_caption, F.text)
async def settings_group_caption_finish(
    message: Message, state: FSMContext, db: Database
) -> None:
    try:
        validate_group_caption_template(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await db.set_setting("group_caption_template", message.text)
    await state.clear()
    await message.answer("✅ Общий текст для нескольких именинников сохранён.", reply_markup=settings_menu())


@router.callback_query(F.data == "settings:time")
async def settings_time_start(callback: CallbackQuery, state: FSMContext, db: Database, config: Config) -> None:
    current = await db.get_setting("publish_time", "09:00")
    await state.set_state(SettingValue.publish_time)
    await callback.answer()
    await callback.message.answer(
        f"Текущее время: <b>{current}</b> ({html.escape(str(config.timezone))}).\n"
        "Введите новое время в формате ЧЧ:ММ.",
        reply_markup=cancel_keyboard(),
    )


@router.message(SettingValue.publish_time, F.text)
async def settings_time_finish(message: Message, state: FSMContext, db: Database) -> None:
    try:
        value = parse_publish_time(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await db.set_setting("publish_time", value)
    await state.clear()
    await message.answer(f"✅ Время публикации изменено на {value}.", reply_markup=settings_menu())


@router.message()
async def fallback(message: Message, is_owner: bool) -> None:
    await message.answer("Используйте меню управления:", reply_markup=main_menu(is_owner))
