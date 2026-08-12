from __future__ import annotations

import sqlite3

from telegram_workflow.domain.models import TelegramMember


class MemberRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert_many(self, members: list[TelegramMember]) -> int:
        rows = [
            (
                m.user_id,
                m.access_hash,
                m.username,
                m.first_name,
                m.last_name,
                m.phone,
                int(m.is_bot),
                int(m.is_deleted),
                m.last_seen,
            )
            for m in members
        ]
        self.connection.executemany(
            """
            INSERT INTO members(
                telegram_user_id, access_hash, username, first_name, last_name,
                phone, is_bot, is_deleted, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                access_hash = COALESCE(excluded.access_hash, members.access_hash),
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                phone = excluded.phone,
                is_bot = excluded.is_bot,
                is_deleted = excluded.is_deleted,
                last_seen = excluded.last_seen,
                updated_at = datetime('now')
            """,
            rows,
        )
        self.connection.commit()
        return len(rows)
