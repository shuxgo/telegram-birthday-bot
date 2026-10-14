from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from .database import Database


class AdminOnlyMiddleware(BaseMiddleware):
    def __init__(self, admin_ids: frozenset[int], db: Database) -> None:
        self.admin_ids = admin_ids
        self.db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        is_owner = bool(user and user.id in self.admin_ids)
        if user and (is_owner or await self.db.is_moderator(user.id)):
            data["is_owner"] = is_owner
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer("⛔️ У вас нет доступа к управлению этим ботом.")
        elif isinstance(event, CallbackQuery):
            await event.answer("Нет доступа", show_alert=True)
        return None
