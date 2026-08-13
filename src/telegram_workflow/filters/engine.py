from __future__ import annotations

import sqlite3

from telegram_workflow.domain.enums import ActivityQuality
from telegram_workflow.domain.models import FilterConfig


class FilterEngine:
    def eligible(self, row: sqlite3.Row, config: FilterConfig) -> bool:
        if config.exclude_bots and bool(row["is_bot"]):
            return False
        if config.exclude_deleted and bool(row["is_deleted"]):
            return False
        username = row["username"] or ""
        if config.require_username and not username:
            return False
        if (
            config.username_contains
            and config.username_contains.casefold() not in username.casefold()
        ):
            return False
        quality = ActivityQuality(row["activity_quality"] or ActivityQuality.UNKNOWN.value)
        if quality == ActivityQuality.UNKNOWN and not config.allow_unknown_activity:
            return False
        return True
