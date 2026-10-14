from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from .utils import DEFAULT_CAPTION, DEFAULT_GROUP_CAPTION


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @asynccontextmanager
    async def connect(self):
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            await connection.close()

    async def initialize(self, default_template_path: Path) -> None:
        async with self.connect() as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS branches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS birthdays (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    birth_date TEXT NOT NULL,
                    position TEXT NOT NULL,
                    branch_id INTEGER NOT NULL REFERENCES branches(id) ON DELETE RESTRICT,
                    photo_file_id TEXT NOT NULL,
                    photo_path TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS publication_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    birthday_id INTEGER NOT NULL REFERENCES birthdays(id) ON DELETE CASCADE,
                    publication_year INTEGER NOT NULL,
                    channel_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 1,
                    last_attempt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    published_at TEXT,
                    UNIQUE(birthday_id, publication_year)
                );

                CREATE TABLE IF NOT EXISTS moderators (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    added_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_birthdays_month_day
                    ON birthdays(substr(birth_date, 6, 2), substr(birth_date, 9, 2));
                """
            )
            defaults = {
                "caption_template": DEFAULT_CAPTION,
                "group_caption_template": DEFAULT_GROUP_CAPTION,
                "publish_time": "09:00",
                "template_path": str(default_template_path),
            }
            await db.executemany(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                defaults.items(),
            )
            await db.execute(
                "UPDATE settings SET value = ? WHERE key = 'caption_template'",
                (DEFAULT_CAPTION,),
            )
            await db.execute("INSERT OR IGNORE INTO branches(name) VALUES (?)", ("Главный филиал",))
            await db.commit()

    async def is_moderator(self, user_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute("SELECT 1 FROM moderators WHERE user_id = ?", (user_id,))
            return await cursor.fetchone() is not None

    async def list_moderators(self) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT user_id, username, full_name, created_at FROM moderators "
                "ORDER BY COALESCE(full_name, username, CAST(user_id AS TEXT)) COLLATE NOCASE"
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def add_moderator(
        self,
        user_id: int,
        added_by: int,
        *,
        username: str | None = None,
        full_name: str | None = None,
    ) -> None:
        async with self.connect() as db:
            await db.execute(
                "INSERT INTO moderators(user_id, username, full_name, added_by) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "username = COALESCE(excluded.username, moderators.username), "
                "full_name = COALESCE(excluded.full_name, moderators.full_name), "
                "added_by = excluded.added_by",
                (user_id, username, full_name, added_by),
            )
            await db.commit()

    async def remove_moderator(self, user_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute("DELETE FROM moderators WHERE user_id = ?", (user_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        async with self.connect() as db:
            cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = await cursor.fetchone()
            return str(row["value"]) if row else default

    async def get_settings(self) -> dict[str, str]:
        async with self.connect() as db:
            cursor = await db.execute("SELECT key, value FROM settings")
            return {str(row["key"]): str(row["value"]) for row in await cursor.fetchall()}

    async def set_setting(self, key: str, value: str) -> None:
        async with self.connect() as db:
            await db.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            await db.commit()

    async def list_branches(self) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT b.id, b.name, COUNT(bd.id) AS birthday_count
                FROM branches b
                LEFT JOIN birthdays bd ON bd.branch_id = b.id AND bd.active = 1
                GROUP BY b.id, b.name
                ORDER BY b.name COLLATE NOCASE
                """
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def add_branch(self, name: str) -> int:
        async with self.connect() as db:
            cursor = await db.execute("INSERT INTO branches(name) VALUES (?)", (name.strip(),))
            await db.commit()
            return int(cursor.lastrowid)

    async def delete_branch(self, branch_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                "DELETE FROM branches WHERE id = ? AND NOT EXISTS "
                "(SELECT 1 FROM birthdays WHERE branch_id = ? AND active = 1)",
                (branch_id, branch_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def add_birthday(
        self,
        *,
        name: str,
        birth_date: str,
        position: str,
        branch_id: int,
        photo_file_id: str,
        photo_path: str,
    ) -> int:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO birthdays(name, birth_date, position, branch_id, photo_file_id, photo_path)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, birth_date, position, branch_id, photo_file_id, photo_path),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def get_birthday(self, birthday_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT bd.*, b.name AS branch_name
                FROM birthdays bd JOIN branches b ON b.id = bd.branch_id
                WHERE bd.id = ? AND bd.active = 1
                """,
                (birthday_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_birthday(self, birthday_id: int, field: str, value: Any) -> bool:
        columns = {
            "name": "name",
            "birth_date": "birth_date",
            "position": "position",
            "branch_id": "branch_id",
            "photo_file_id": "photo_file_id",
            "photo_path": "photo_path",
        }
        if field not in columns:
            raise ValueError("Unsupported birthday field")
        async with self.connect() as db:
            cursor = await db.execute(
                f"UPDATE birthdays SET {columns[field]} = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND active = 1",
                (value, birthday_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def update_birthday_photo(self, birthday_id: int, file_id: str, path: str) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                "UPDATE birthdays SET photo_file_id = ?, photo_path = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND active = 1",
                (file_id, path, birthday_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_birthday(self, birthday_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute("DELETE FROM birthdays WHERE id = ?", (birthday_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def list_birthdays_for_month(self, year: int, month: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT bd.*, b.name AS branch_name
                FROM birthdays bd JOIN branches b ON b.id = bd.branch_id
                WHERE bd.active = 1 AND CAST(substr(bd.birth_date, 6, 2) AS INTEGER) = ?
                ORDER BY CAST(substr(bd.birth_date, 9, 2) AS INTEGER), bd.name COLLATE NOCASE
                """,
                (month,),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def list_all_birthdays(self) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT bd.*, b.name AS branch_name
                FROM birthdays bd JOIN branches b ON b.id = bd.branch_id
                WHERE bd.active = 1
                ORDER BY CAST(substr(bd.birth_date, 6, 2) AS INTEGER),
                         CAST(substr(bd.birth_date, 9, 2) AS INTEGER),
                         bd.name COLLATE NOCASE
                """
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def list_due_birthdays(self, now: datetime) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT bd.*, b.name AS branch_name,
                       pl.status AS publication_status,
                       COALESCE(pl.attempt_count, 0) AS attempt_count,
                       pl.last_attempt
                FROM birthdays bd
                JOIN branches b ON b.id = bd.branch_id
                LEFT JOIN publication_log pl
                  ON pl.birthday_id = bd.id AND pl.publication_year = ?
                WHERE bd.active = 1
                  AND CAST(substr(bd.birth_date, 6, 2) AS INTEGER) = ?
                  AND CAST(substr(bd.birth_date, 9, 2) AS INTEGER) = ?
                  AND (
                    pl.id IS NULL OR (
                      pl.status = 'failed'
                      AND pl.attempt_count < 10
                      AND datetime(pl.last_attempt) <= datetime('now', '-15 minutes')
                    )
                  )
                ORDER BY bd.id
                """,
                (now.year, now.month, now.day),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def record_publication(
        self,
        birthday_id: int,
        year: int,
        channel_id: str,
        *,
        success: bool,
        error: str | None = None,
    ) -> None:
        status = "published" if success else "failed"
        published_at = (
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if success else None
        )
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO publication_log(
                    birthday_id, publication_year, channel_id, status, error,
                    attempt_count, last_attempt, published_at
                ) VALUES (?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(birthday_id, publication_year) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    status = excluded.status,
                    error = excluded.error,
                    attempt_count = publication_log.attempt_count + 1,
                    last_attempt = CURRENT_TIMESTAMP,
                    published_at = excluded.published_at
                """,
                (birthday_id, year, channel_id, status, error, published_at),
            )
            await db.commit()

    async def publication_stats(self, year: int) -> dict[str, int]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT
                  SUM(CASE WHEN status = 'published' THEN 1 ELSE 0 END) AS published,
                  SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
                FROM publication_log WHERE publication_year = ?
                """,
                (year,),
            )
            row = await cursor.fetchone()
            return {"published": int(row["published"] or 0), "failed": int(row["failed"] or 0)}
