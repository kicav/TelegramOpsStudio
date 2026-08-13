from __future__ import annotations

import sqlite3

from telegram_workflow.domain.enums import AccountState


class AccountRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def add(
        self,
        phone: str,
        session_ref: str | None = None,
        api_profile_id: int | None = None,
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO accounts(phone, session_ref, api_profile_id)
            VALUES (?, ?, ?)
            ON CONFLICT(phone) DO UPDATE SET
                session_ref = COALESCE(excluded.session_ref, accounts.session_ref),
                api_profile_id = COALESCE(excluded.api_profile_id, accounts.api_profile_id),
                updated_at = datetime('now')
            """,
            (phone, session_ref, api_profile_id),
        )
        self.connection.commit()
        if cursor.lastrowid:
            return int(cursor.lastrowid)
        row = self.connection.execute(
            "SELECT id FROM accounts WHERE phone = ?", (phone,)
        ).fetchone()
        if row is None:
            raise RuntimeError("Account upsert did not return a row")
        return int(row["id"])

    def set_state(
        self,
        account_id: int,
        state: AccountState,
        cooldown_until: str | None = None,
    ) -> None:
        self.connection.execute(
            """
            UPDATE accounts
            SET state = ?, cooldown_until = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (state.value, cooldown_until, account_id),
        )
        self.connection.commit()

    def ready_ids(self) -> list[int]:
        rows = self.connection.execute(
            "SELECT id FROM accounts WHERE state = ? ORDER BY id",
            (AccountState.READY.value,),
        ).fetchall()
        return [int(row["id"]) for row in rows]

    def count_by_state(self, state: AccountState) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) FROM accounts WHERE state = ?", (state.value,)
        ).fetchone()
        return int(row[0]) if row else 0

    def list_all(self) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT a.*, p.name AS api_profile_name, p.api_id, p.api_hash_secret_ref
            FROM accounts a
            LEFT JOIN api_profiles p ON p.id = a.api_profile_id
            ORDER BY a.id
            """
        ).fetchall()

    def get_with_profile(self, account_id: int) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT a.*, p.name AS api_profile_name, p.api_id, p.api_hash_secret_ref
            FROM accounts a
            LEFT JOIN api_profiles p ON p.id = a.api_profile_id
            WHERE a.id = ?
            """,
            (account_id,),
        ).fetchone()
