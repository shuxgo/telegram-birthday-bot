from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Config:
    token: str
    admin_ids: frozenset[int]
    timezone: ZoneInfo
    data_dir: Path

    @property
    def database_path(self) -> Path:
        return self.data_dir / "birthday_bot.sqlite3"


def load_config() -> Config:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")

    raw_admins = os.getenv("ADMIN_IDS", "").strip()
    if not raw_admins:
        raise RuntimeError("ADMIN_IDS is not set")
    try:
        admin_ids = frozenset(int(item.strip()) for item in raw_admins.split(",") if item.strip())
    except ValueError as exc:
        raise RuntimeError("ADMIN_IDS must contain comma-separated Telegram user IDs") from exc
    if not admin_ids:
        raise RuntimeError("ADMIN_IDS is empty")

    timezone_name = os.getenv("TIMEZONE", "Asia/Tashkent").strip()
    try:
        timezone = ZoneInfo(timezone_name)
    except Exception as exc:
        raise RuntimeError(f"Unknown TIMEZONE: {timezone_name}") from exc

    data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "photos").mkdir(exist_ok=True)
    (data_dir / "cards").mkdir(exist_ok=True)
    (data_dir / "templates").mkdir(exist_ok=True)
    return Config(token=token, admin_ids=admin_ids, timezone=timezone, data_dir=data_dir)

