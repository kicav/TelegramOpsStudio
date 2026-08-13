from __future__ import annotations

import sqlite3

from telegram_workflow.domain.models import TelegramMember


class MemberRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert_many(self, members: list[TelegramMember]) -> int:
        if not members:
            return 0
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
                m.activity_quality.value,
            )
            for m in members
        ]
        self.connection.executemany(
            """
            INSERT INTO members(
                telegram_user_id, access_hash, username, first_name, last_name,
                phone, is_bot, is_deleted, last_seen, activity_quality
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                access_hash = COALESCE(excluded.access_hash, members.access_hash),
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                phone = excluded.phone,
                is_bot = excluded.is_bot,
                is_deleted = excluded.is_deleted,
                last_seen = excluded.last_seen,
                activity_quality = excluded.activity_quality,
                updated_at = datetime('now')
            """,
            rows,
        )
        self.connection.commit()
        return len(rows)

    def ids_for_user_ids(self, user_ids: list[int]) -> dict[int, int]:
        if not user_ids:
            return {}
        placeholders = ",".join("?" for _ in user_ids)
        rows = self.connection.execute(
            f"SELECT id, telegram_user_id FROM members WHERE telegram_user_id IN ({placeholders})",
            user_ids,
        ).fetchall()
        return {int(row["telegram_user_id"]): int(row["id"]) for row in rows}

    def count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM members").fetchone()
        return int(row[0]) if row else 0

    def list_rows(
        self,
        *,
        search: str = "",
        consent_state: str = "ALL",
        source_id: int | None = None,
        limit: int = 5000,
    ) -> tuple[list[sqlite3.Row], int]:
        clauses: list[str] = []
        params: list[object] = []
        joins = ""
        if source_id is not None:
            joins = " JOIN source_members sm ON sm.member_id = m.id "
            clauses.append("sm.source_id = ?")
            params.append(source_id)
        normalized_consent = consent_state.strip().upper()
        if normalized_consent in {"UNKNOWN", "OPTED_IN", "OPTED_OUT"}:
            clauses.append("m.consent_state = ?")
            params.append(normalized_consent)
        search = search.strip()
        if search:
            token = f"%{search}%"
            clauses.append(
                "(CAST(m.telegram_user_id AS TEXT) LIKE ? OR m.username LIKE ? "
                "OR m.first_name LIKE ? OR m.last_name LIKE ? OR m.phone LIKE ?)"
            )
            params.extend([token] * 5)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        count_row = self.connection.execute(
            f"SELECT COUNT(*) FROM members m{joins}{where}", params
        ).fetchone()
        total = int(count_row[0]) if count_row else 0
        rows = self.connection.execute(
            f"SELECT DISTINCT m.* FROM members m{joins}{where} ORDER BY m.id DESC LIMIT ?",
            [*params, max(1, min(int(limit), 50_000))],
        ).fetchall()
        return rows, total

    def set_consent(
        self, member_ids: list[int], consent_state: str, *, notes: str = ""
    ) -> int:
        normalized = consent_state.strip().upper()
        if normalized not in {"UNKNOWN", "OPTED_IN", "OPTED_OUT"}:
            raise ValueError("Invalid consent state")
        unique_ids = sorted({int(value) for value in member_ids if int(value) > 0})
        if not unique_ids:
            return 0
        placeholders = ",".join("?" for _ in unique_ids)
        cursor = self.connection.execute(
            f"""
            UPDATE members
            SET consent_state = ?, consent_updated_at = datetime('now'), notes = ?,
                updated_at = datetime('now')
            WHERE id IN ({placeholders})
            """,
            [normalized, notes.strip(), *unique_ids],
        )
        self.connection.commit()
        return int(cursor.rowcount)

