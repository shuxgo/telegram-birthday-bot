from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .database import Database
from .image_service import render_card
from .utils import render_caption


logger = logging.getLogger(__name__)


class BirthdayPublisher:
    def __init__(self, bot: Bot, db: Database, data_dir: Path, timezone: ZoneInfo) -> None:
        self.bot = bot
        self.db = db
        self.data_dir = data_dir
        self.timezone = timezone
        self.scheduler = AsyncIOScheduler(timezone=timezone)

    async def check_and_publish(self) -> None:
        now = datetime.now(self.timezone)
        settings = await self.db.get_settings()
        channel_id = settings.get("channel_id")
        if not channel_id:
            return
        publish_time = settings.get("publish_time", "09:00")
        hour, minute = (int(part) for part in publish_time.split(":"))
        if (now.hour, now.minute) < (hour, minute):
            return

        birthdays = await self.db.list_due_birthdays(now)
        for birthday in birthdays:
            try:
                output = self.data_dir / "cards" / f"birthday-{birthday['id']}-{now.year}.jpg"
                overlay_path = Path(settings["template_path"])
                render_card(Path(birthday["photo_path"]), overlay_path, output)
                caption = render_caption(settings["caption_template"], birthday)
                await self.bot.send_photo(
                    chat_id=int(channel_id) if channel_id.lstrip("-").isdigit() else channel_id,
                    photo=FSInputFile(output),
                    caption=caption,
                )
                await self.db.record_publication(
                    int(birthday["id"]), now.year, channel_id, success=True
                )
                logger.info("Published birthday %s to %s", birthday["id"], channel_id)
            except Exception as exc:
                logger.exception("Could not publish birthday %s", birthday["id"])
                await self.db.record_publication(
                    int(birthday["id"]), now.year, channel_id,
                    success=False, error=str(exc)[:1000],
                )

    def start(self) -> None:
        self.scheduler.add_job(
            self.check_and_publish,
            "cron",
            minute="*",
            second=0,
            id="birthday-publisher",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
        self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
