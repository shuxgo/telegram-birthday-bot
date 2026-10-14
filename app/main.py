from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from .config import load_config
from .database import Database
from .handlers import router
from .image_service import ensure_default_template
from .middleware import AdminOnlyMiddleware
from .scheduler import BirthdayPublisher


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    config = load_config()
    default_template = ensure_default_template(config.data_dir / "templates" / "default.png")
    db = Database(config.database_path)
    await db.initialize(default_template)

    bot = Bot(config.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher(storage=MemoryStorage())
    router.message.outer_middleware(AdminOnlyMiddleware(config.admin_ids, db))
    router.callback_query.outer_middleware(AdminOnlyMiddleware(config.admin_ids, db))
    dispatcher.include_router(router)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть меню"),
            BotCommand(command="menu", description="Главное меню"),
        ]
    )
    publisher = BirthdayPublisher(bot, db, config.data_dir, config.timezone)
    publisher.start()

    try:
        # Catches today's post if the process was restarted after publication time.
        await publisher.check_and_publish()
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(bot, db=db, config=config)
    finally:
        publisher.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
