from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from PIL import Image

from app.database import Database
from app.image_service import ensure_default_template, render_card, validate_overlay
from app.keyboards import main_menu, settings_menu
from app.utils import (
    DEFAULT_GROUP_CAPTION,
    month_bounds,
    parse_birth_date,
    parse_publish_time,
    render_caption,
    render_group_caption,
)


class DateTests(unittest.TestCase):
    def test_short_birth_date_is_recurring_leap_safe(self) -> None:
        self.assertEqual(parse_birth_date("29.02").isoformat(), "2000-02-29")

    def test_full_birth_date(self) -> None:
        self.assertEqual(parse_birth_date("7-4-1995").isoformat(), "1995-04-07")

    def test_invalid_birth_date(self) -> None:
        with self.assertRaises(ValueError):
            parse_birth_date("31.02")

    def test_publish_time(self) -> None:
        self.assertEqual(parse_publish_time("9:05"), "09:05")
        with self.assertRaises(ValueError):
            parse_publish_time("24:00")

    def test_month_rollover(self) -> None:
        now = datetime(2026, 12, 15)
        self.assertEqual(month_bounds(now, 1), (2027, 1))


class CaptionTests(unittest.TestCase):
    def test_values_are_html_escaped(self) -> None:
        caption = render_caption(
            "{name} / {position} / {branch} / {date}",
            {
                "name": "A < B",
                "position": "R&D",
                "branch_name": "Центр",
                "birth_date": "2000-01-02",
            },
        )
        self.assertIn("A &lt; B", caption)
        self.assertIn("R&amp;D", caption)

    def test_escaped_newlines_are_rendered_as_paragraphs(self) -> None:
        caption = render_caption(
            "Заголовок\\n\\n<b>{name}</b>",
            {
                "name": "Анна",
                "position": "специалист",
                "branch_name": "Центр",
                "birth_date": "2000-01-02",
            },
        )
        self.assertEqual(caption, "Заголовок\n\n<b>Анна</b>")

    def test_group_caption_lists_nine_people_within_telegram_limit(self) -> None:
        rows = [
            {
                "name": f"Сотрудник {index}",
                "position": "ведущий специалист",
                "branch_name": "Главный филиал",
                "birth_date": "2000-01-02",
            }
            for index in range(1, 10)
        ]
        caption = render_group_caption(DEFAULT_GROUP_CAPTION, rows)
        self.assertIn("9. <b>Сотрудник 9</b>", caption)
        self.assertLessEqual(len(caption), 1000)


class ImageTests(unittest.TestCase):
    def test_default_overlay_and_render(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            overlay = ensure_default_template(root / "overlay.png")
            self.assertEqual(validate_overlay(overlay), (1080, 1080))
            photo = root / "photo.jpg"
            Image.new("RGB", (800, 1200), "red").save(photo)
            output = render_card(photo, overlay, root / "card.jpg")
            self.assertTrue(output.exists())
            with Image.open(output) as result:
                self.assertEqual(result.size, (1080, 1080))


class KeyboardTests(unittest.TestCase):
    def test_persistent_panel_has_only_expected_buttons(self) -> None:
        moderator_texts = [button.text for row in main_menu(False).keyboard for button in row]
        owner_texts = [button.text for row in main_menu(True).keyboard for button in row]
        self.assertEqual(
            moderator_texts,
            ["🎂 Новый именинник", "📅 Именинники", "⚙️ Настройки"],
        )
        self.assertEqual(owner_texts[-1], "👥 Модераторы")

    def test_branches_are_inside_settings(self) -> None:
        callbacks = [
            button.callback_data
            for row in settings_menu().inline_keyboard
            for button in row
        ]
        self.assertIn("menu:branches", callbacks)


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_moderator_access_can_be_added_and_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            overlay = ensure_default_template(root / "overlay.png")
            db = Database(root / "test.sqlite3")
            await db.initialize(overlay)
            self.assertFalse(await db.is_moderator(555))
            await db.add_moderator(555, 426250217, username="moderator")
            self.assertTrue(await db.is_moderator(555))
            self.assertEqual((await db.list_moderators())[0]["user_id"], 555)
            self.assertTrue(await db.remove_moderator(555))
            self.assertFalse(await db.is_moderator(555))

    async def test_annual_publication_is_sent_only_once_per_year(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            overlay = ensure_default_template(root / "overlay.png")
            db = Database(root / "test.sqlite3")
            await db.initialize(overlay)
            branches = await db.list_branches()
            birthday_id = await db.add_birthday(
                name="Анна Иванова",
                birth_date="1990-10-14",
                position="специалист",
                branch_id=branches[0]["id"],
                photo_file_id="telegram-file-id",
                photo_path=str(root / "photo.jpg"),
            )
            due = await db.list_due_birthdays(datetime(2026, 10, 14, 9, 0))
            self.assertEqual([row["id"] for row in due], [birthday_id])
            await db.record_publication(birthday_id, 2026, "-1001", success=True)
            self.assertEqual(await db.list_due_birthdays(datetime(2026, 10, 14, 10, 0)), [])
            due_next_year = await db.list_due_birthdays(datetime(2027, 10, 14, 9, 0))
            self.assertEqual([row["id"] for row in due_next_year], [birthday_id])


if __name__ == "__main__":
    unittest.main()
