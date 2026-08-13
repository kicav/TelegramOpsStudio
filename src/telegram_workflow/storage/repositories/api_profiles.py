from __future__ import annotations

import sqlite3


class ApiProfileRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert(self, *, name: str, api_id: int, api_hash_secret_ref: str) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO api_profiles(name, api_id, api_hash_secret_ref)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                api_id = excluded.api_id,
                api_hash_secret_ref = excluded.api_hash_secret_ref,
                enabled = 1,
                updated_at = datetime('now')
            """,
            (name, api_id, api_hash_secret_ref),
        )
        self.connection.commit()
        if cursor.lastrowid:
            return int(cursor.lastrowid)
        row = self.connection.execute(
            "SELECT id FROM api_profiles WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            raise RuntimeError("API profile upsert did not return a row")
        return int(row["id"])

    def get(self, profile_id: int) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM api_profiles WHERE id = ?", (profile_id,)
        ).fetchone()

    def get_by_name(self, name: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM api_profiles WHERE name = ?", (name,)
        ).fetchone()
