from __future__ import annotations

import sqlite3

from telegram_workflow.domain.models import ActionOutcome


class AttemptRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def start(self, job_member_id: int, account_id: int | None, attempt_no: int) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO attempts(job_member_id, account_id, attempt_no)
            VALUES (?, ?, ?)
            """,
            (job_member_id, account_id, attempt_no),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def finish(self, attempt_id: int, outcome: ActionOutcome) -> None:
        self.connection.execute(
            """
            UPDATE attempts SET finished_at = datetime('now'), result = ?, error_scope = ?,
                error_code = ?, error_message = ? WHERE id = ?
            """,
            (outcome.result.value, outcome.scope.value, outcome.code, outcome.message, attempt_id),
        )
        self.connection.commit()

    def finish_latest_open(self, job_member_id: int, outcome: ActionOutcome) -> bool:
        row = self.connection.execute(
            """
            SELECT id FROM attempts
            WHERE job_member_id = ? AND finished_at IS NULL
            ORDER BY attempt_no DESC LIMIT 1
            """,
            (job_member_id,),
        ).fetchone()
        if row is None:
            return False
        self.finish(int(row["id"]), outcome)
        return True

