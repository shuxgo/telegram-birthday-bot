from __future__ import annotations

import html
import re
from datetime import date, datetime


MONTHS_RU = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)

DEFAULT_CAPTION = (
    "🎉 Поздравляем <b>[ФИО]</b>, [Должность] филиала «[Филиал]», с днём рождения!\n\n"
    "Желаем крепкого здоровья, благополучия, вдохновения и новых успехов! 💙"
)

DEFAULT_GROUP_CAPTION = (
    "🎉 Поздравляем с днём рождения [Список]!\n\n"
    "Желаем крепкого здоровья, благополучия, вдохновения и новых успехов! 💙"
)

ALLOWED_PLACEHOLDERS = {"name", "position", "branch", "date"}
ALLOWED_GROUP_PLACEHOLDERS = {"people", "count"}
RUSSIAN_PLACEHOLDERS = {"ФИО", "Должность", "Филиал", "Дата"}
RUSSIAN_GROUP_PLACEHOLDERS = {"Список", "Количество"}


def parse_birth_date(value: str) -> date:
    cleaned = value.strip()
    separator = r"[\s./\\_-]+"
    iso_match = re.fullmatch(rf"(\d{{4}}){separator}(\d{{1,2}}){separator}(\d{{1,2}})", cleaned)
    usual_match = re.fullmatch(rf"(\d{{1,2}}){separator}(\d{{1,2}})(?:{separator}(\d{{2}}|\d{{4}}))?", cleaned)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
    elif usual_match:
        day = int(usual_match.group(1))
        month = int(usual_match.group(2))
        year_text = usual_match.group(3)
        year = 2000 if year_text is None else int(year_text)
        if year_text is not None and len(year_text) == 2:
            year += 2000 if year < 50 else 1900
    else:
        raise ValueError("Введите дату, например 15.10 или 15-10")
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
    curly = set(re.findall(r"\{([^{}]+)\}", template))
    square = set(re.findall(r"\[([^\[\]]+)\]", template))
    unknown = (curly - ALLOWED_PLACEHOLDERS) | (square - RUSSIAN_PLACEHOLDERS)
    if unknown:
        raise ValueError(f"Неизвестные переменные: {', '.join(sorted(unknown))}")


def validate_group_caption_template(template: str) -> None:
    if len(template) > 900:
        raise ValueError("Шаблон слишком длинный — максимум 900 символов")
    curly = set(re.findall(r"\{([^{}]+)\}", template))
    square = set(re.findall(r"\[([^\[\]]+)\]", template))
    unknown = (curly - ALLOWED_GROUP_PLACEHOLDERS) | (square - RUSSIAN_GROUP_PLACEHOLDERS)
    if unknown:
        raise ValueError(f"Неизвестные переменные: {', '.join(sorted(unknown))}")
    if "people" not in curly and "Список" not in square:
        raise ValueError("Добавьте обязательную переменную [Список]")


def render_caption(template: str, birthday: dict) -> str:
    values = {
        "name": html.escape(str(birthday["name"])),
        "position": html.escape(str(birthday["position"])),
        "branch": html.escape(str(birthday["branch_name"])),
        "date": display_birth_date(str(birthday["birth_date"])),
    }
    result = template.replace("\\n", "\n")
    replacements = {
        "[ФИО]": values["name"], "[Должность]": values["position"],
        "[Филиал]": values["branch"], "[Дата]": values["date"],
        "{name}": values["name"], "{position}": values["position"],
        "{branch}": values["branch"], "{date}": values["date"],
    }
    for placeholder, replacement in replacements.items():
        result = result.replace(placeholder, replacement)
    return result


def _compact(value: object, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_group_caption(template: str, birthdays: list[dict]) -> str:
    entries = [
        f"<b>{html.escape(_compact(row['name'], 36))}</b> "
        f"({html.escape(_compact(row['position'], 28))}, филиал "
        f"«{html.escape(_compact(row['branch_name'], 22))}»)"
        for row in birthdays
    ]
    people = entries[0] if len(entries) == 1 else (
        " и ".join(entries) if len(entries) == 2 else ", ".join(entries[:-1]) + " и " + entries[-1]
    )
    caption = template.replace("\\n", "\n")
    for placeholder, replacement in {
        "[Список]": people, "[Количество]": str(len(birthdays)),
        "{people}": people, "{count}": str(len(birthdays)),
    }.items():
        caption = caption.replace(placeholder, replacement)
    if len(caption) <= 1000:
        return caption
    names_list = [f"<b>{html.escape(_compact(row['name'], 55))}</b>" for row in birthdays]
    names = " и ".join(names_list) if len(names_list) == 2 else ", ".join(names_list[:-1]) + " и " + names_list[-1]
    return (
        f"🎉 Поздравляем с днём рождения {names}!\n\n"
        "Желаем здоровья, благополучия, вдохновения и новых успехов! 💙"
    )


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
