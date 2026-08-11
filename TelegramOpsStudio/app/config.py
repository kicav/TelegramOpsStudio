from __future__ import annotations

from pathlib import Path

APP_NAME = "TelegramOpsStudio"
APP_VERSION = "0.1.0"
DATA_DIR = Path.home() / ".telegram_ops_studio"
SESSIONS_DIR = DATA_DIR / "sessions"
EXPORTS_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "telegram_ops.sqlite3"

DEFAULTS = {
    "invite_delay_min": "8",
    "invite_delay_max": "15",
    "message_delay_min": "8",
    "message_delay_max": "15",
    "daily_invite_cap": "20",
    "campaign_limit": "50",
    "update_manifest_url": "",
}


def ensure_dirs() -> None:
    for path in (DATA_DIR, SESSIONS_DIR, EXPORTS_DIR):
        path.mkdir(parents=True, exist_ok=True)
