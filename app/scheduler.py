from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .database import Database
from .image_service import render_card
from .utils import DEFAULT_GROUP_CAPTION, render_caption, render_group_caption


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
        for start in range(0, len(birthdays), 9):
            batch = birthdays[start : start + 9]
            try:
                overlay_path = Path(settings["template_path"])
                outputs: list[Path] = []
                for birthday in batch:
                    output = self.data_dir / "cards" / f"birthday-{birthday['id']}-{now.year}.jpg"
                    render_card(Path(birthday["photo_path"]), overlay_path, output)
                    outputs.append(output)
                caption = (
                    render_caption(settings["caption_template"], batch[0])
                    if len(batch) == 1
                    else render_group_caption(
                        settings.get("group_caption_template", DEFAULT_GROUP_CAPTION), batch
                    )
                )
                target = int(channel_id) if channel_id.lstrip("-").isdigit() else channel_id
                if len(batch) == 1:
                    await self.bot.send_photo(
                        chat_id=target, photo=FSInputFile(outputs[0]), caption=caption
                    )
                else:
                    media = [
                        InputMediaPhoto(
                            media=FSInputFile(output),
                            caption=caption if index == 0 else None,
                        )
                        for index, output in enumerate(outputs)
                    ]
                    await self.bot.send_media_group(chat_id=target, media=media)
                for birthday in batch:
                    await self.db.record_publication(
                        int(birthday["id"]), now.year, channel_id, success=True
                    )
                logger.info("Published birthday batch %s to %s", [row["id"] for row in batch], channel_id)
            except Exception as exc:
                logger.exception("Could not publish birthday batch %s", [row["id"] for row in batch])
                for birthday in batch:
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
