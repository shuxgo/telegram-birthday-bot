from __future__ import annotations

import html
import re
import string
from datetime import date, datetime


MONTHS_RU = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)

DEFAULT_CAPTION = (
    "🎉 <b>Поздравляем с днём рождения!</b>\n\n"
    "Сегодня день рождения отмечает <b>{name}</b> — {position}, "
    "филиал «{branch}».\n\n"
    "Желаем крепкого здоровья, счастья, вдохновения и новых профессиональных успехов! 🎂"
)

ALLOWED_PLACEHOLDERS = {"name", "position", "branch", "date"}


def parse_birth_date(value: str) -> date:
    cleaned = value.strip().replace("/", ".").replace("-", ".")
    if not re.fullmatch(r"\d{1,2}\.\d{1,2}(?:\.\d{4})?", cleaned):
        raise ValueError("Введите дату в формате ДД.ММ или ДД.ММ.ГГГГ")
    parts = [int(item) for item in cleaned.split(".")]
    day, month = parts[0], parts[1]
    year = parts[2] if len(parts) == 3 else 2000
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ValueError("Такой даты не существует") from exc


def display_birth_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    return f"{parsed.day} {MONTHS_RU[parsed.month - 1]}"


def validate_caption_template(template: str) -> None:
    if len(template) > 900:
        raise ValueError("Шаблон слишком длинный — максимум 900 символов")
    try:
        fields = {field for _, field, _, _ in string.Formatter().parse(template) if field}
    except ValueError as exc:
        raise ValueError("Проверьте парные фигурные скобки") from exc
    unknown = fields - ALLOWED_PLACEHOLDERS
    if unknown:
        raise ValueError(f"Неизвестные переменные: {', '.join(sorted(unknown))}")
    try:
        template.format(name="Имя", position="должность", branch="филиал", date="1 января")
    except (KeyError, ValueError) as exc:
        raise ValueError("Не удалось обработать шаблон") from exc


def render_caption(template: str, birthday: dict) -> str:
    values = {
        "name": html.escape(str(birthday["name"])),
        "position": html.escape(str(birthday["position"])),
        "branch": html.escape(str(birthday["branch_name"])),
        "date": display_birth_date(str(birthday["birth_date"])),
    }
    return template.format_map(values)


def parse_publish_time(value: str) -> str:
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value)
    if not match:
        raise ValueError("Введите время в формате ЧЧ:ММ, например 09:00")
    hour, minute = int(match.group(1)), int(match.group(2))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Некорректное время")
    return f"{hour:02d}:{minute:02d}"


def month_bounds(now: datetime, offset: int = 0) -> tuple[int, int]:
    month_index = now.year * 12 + now.month - 1 + offset
    return month_index // 12, month_index % 12 + 1

