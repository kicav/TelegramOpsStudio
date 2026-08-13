from __future__ import annotations

import json
import sqlite3


class SettingsRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def set(self, key: str, value: object) -> None:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
        self.connection.execute(
            """
            INSERT INTO settings(key, value_json) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json,
                updated_at = datetime('now')
            """,
            (key, payload),
        )
        self.connection.commit()

    def get(self, key: str, default: object | None = None) -> object:
        row = self.connection.execute(
            "SELECT value_json FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return default if row is None else json.loads(row["value_json"])
