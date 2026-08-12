from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "TelegramOpsStudio"
APP_DISPLAY_NAME = "Telegram Ops Studio"
APP_VERSION = "1.0.0"


def _data_dir() -> Path:
    override = os.environ.get("TELEGRAM_OPS_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".telegram_ops_studio"


DATA_DIR = _data_dir()
SESSIONS_DIR = DATA_DIR / "sessions"
EXPORTS_DIR = DATA_DIR / "exports"
DOWNLOADS_DIR = DATA_DIR / "downloads"
DB_PATH = DATA_DIR / "telegram_ops.sqlite3"

DEFAULTS = {
    "invite_delay_min": "8",
    "invite_delay_max": "15",
    "message_delay_min": "8",
    "message_delay_max": "15",
    "daily_invite_cap": "20",
    "campaign_limit": "50",
    "scan_limit": "5000",
    "archive_limit": "200",
    "update_manifest_url": "",
}


def ensure_dirs() -> None:
    for path in (DATA_DIR, SESSIONS_DIR, EXPORTS_DIR, DOWNLOADS_DIR):
        path.mkdir(parents=True, exist_ok=True)
