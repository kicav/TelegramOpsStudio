from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

from telegram_workflow.domain.enums import JobMemberState, JobState
from telegram_workflow.domain.models import ClaimedJobMember
from telegram_workflow.domain.state_machine import ensure_job_transition


def _sqlite_after(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")


class JobRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create(
        self,
        *,
        name: str,
        source_id: int,
        target_id: int,
        target_snapshot_id: int | None,
        filter_snapshot: dict[str, object],
        selected_accounts: list[int] | None = None,
        range_start: int | None = None,
        range_end: int | None = None,
        max_items: int | None = None,
    ) -> int:
        source_row = self.connection.execute(
            "SELECT telegram_entity_id FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
        target_row = self.connection.execute(
            "SELECT telegram_entity_id FROM targets WHERE id = ?", (target_id,)
        ).fetchone()
        if source_row is None or target_row is None:
            raise ValueError("Source or target record does not exist")
        source_entity_id = source_row["telegram_entity_id"]
        target_entity_id = target_row["telegram_entity_id"]
        if source_entity_id is not None and source_entity_id == target_entity_id:
            raise ValueError("Source and target resolve to the same Telegram entity")
        cursor = self.connection.execute(
            """
            INSERT INTO jobs(
                name, source_id, target_id, target_snapshot_id,
                filter_snapshot_json, selected_accounts_json, range_start, range_end,
                max_items, state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                source_id,
                target_id,
                target_snapshot_id,
                json.dumps(filter_snapshot, sort_keys=True),
                json.dumps(selected_accounts or []),
                range_start,
                range_end,
                max_items,
                JobState.READY.value,
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def set_state(self, job_id: int, state: JobState) -> None:
        row = self.connection.execute(
            "SELECT state FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Job {job_id} not found")
        current = JobState(row["state"])
        ensure_job_transition(current, state)
        if current == state:
            return
        if state == JobState.RUNNING:
            self.connection.execute(
                "UPDATE jobs SET state = ?, "
                "started_at = COALESCE(started_at, datetime('now')) WHERE id = ?",
                (state.value, job_id),
            )
        elif state in {JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED}:
            self.connection.execute(
                "UPDATE jobs SET state = ?, finished_at = datetime('now') WHERE id = ?",
                (state.value, job_id),
            )
        else:
            self.connection.execute("UPDATE jobs SET state = ? WHERE id = ?", (state.value, job_id))
        self.connection.commit()

    def refresh_counts(self, job_id: int) -> None:
        row = self.connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN state = 'SUCCESS' THEN 1 ELSE 0 END) AS success,
                   SUM(CASE WHEN state = 'SKIPPED' THEN 1 ELSE 0 END) AS skipped,
                   SUM(CASE WHEN state = 'FINAL_FAIL' THEN 1 ELSE 0 END) AS failed
            FROM job_members WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        self.connection.execute(
            "UPDATE jobs SET total = ?, success = ?, skipped = ?, failed = ? WHERE id = ?",
            (
                int(row["total"] or 0),
                int(row["success"] or 0),
                int(row["skipped"] or 0),
                int(row["failed"] or 0),
                job_id,
            ),
        )
        self.connection.commit()

    def counts_by_state(self, state: JobState) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE state = ?", (state.value,)
        ).fetchone()
        return int(row[0]) if row else 0


class JobMemberRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def enqueue(self, job_id: int, member_ids: list[int]) -> int:
        if not member_ids:
            return 0
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO job_members(job_id, member_id, state)
            VALUES (?, ?, ?)
            """,
            [(job_id, member_id, JobMemberState.READY.value) for member_id in member_ids],
        )
        self.connection.commit()
        return self.connection.execute(
            "SELECT COUNT(*) FROM job_members WHERE job_id = ?", (job_id,)
        ).fetchone()[0]

    def previous_success_member_ids(self, source_id: int, target_id: int) -> set[int]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT jm.member_id
            FROM job_members jm
            JOIN jobs j ON j.id = jm.job_id
            WHERE j.source_id = ? AND j.target_id = ? AND jm.state = 'SUCCESS'
            """,
            (source_id, target_id),
        ).fetchall()
        return {int(row["member_id"]) for row in rows}

    def claim_next(
        self, job_id: int, worker_id: str, lease_seconds: int
    ) -> ClaimedJobMember | None:
        if self.connection.in_transaction:
            self.connection.commit()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                """
                SELECT jm.id, jm.job_id, jm.member_id, jm.attempt_count,
                       m.telegram_user_id, m.access_hash, m.username
                FROM job_members jm
                JOIN members m ON m.id = jm.member_id
                WHERE jm.job_id = ? AND jm.state = 'READY'
                  AND (jm.next_retry_at IS NULL OR jm.next_retry_at <= datetime('now'))
                ORDER BY jm.priority, jm.id
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                self.connection.commit()
                return None
            updated = self.connection.execute(
                """
                UPDATE job_members
                SET state = ?, lease_owner = ?, lease_until = ?, updated_at = datetime('now')
                WHERE id = ? AND state = 'READY'
                """,
                (
                    JobMemberState.PROCESSING.value,
                    worker_id,
                    _sqlite_after(lease_seconds),
                    int(row["id"]),
                ),
            )
            if updated.rowcount != 1:
                self.connection.rollback()
                return None
            self.connection.commit()
            return ClaimedJobMember(
                job_member_id=int(row["id"]),
                job_id=int(row["job_id"]),
                member_id=int(row["member_id"]),
                telegram_user_id=int(row["telegram_user_id"]),
                access_hash=row["access_hash"],
                username=row["username"],
                attempt_count=int(row["attempt_count"]),
            )
        except Exception:
            self.connection.rollback()
            raise

    def complete(
        self,
        job_member_id: int,
        state: JobMemberState,
        *,
        account_id: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if state not in {JobMemberState.SUCCESS, JobMemberState.SKIPPED, JobMemberState.FINAL_FAIL}:
            raise ValueError(f"Invalid terminal job member state: {state}")
        cursor = self.connection.execute(
            """
            UPDATE job_members SET state = ?, lease_owner = NULL, lease_until = NULL,
                last_account_id = ?, last_error_code = ?, last_error_message = ?,
                attempt_count = attempt_count + 1, completed_at = datetime('now'),
                updated_at = datetime('now') WHERE id = ? AND state = ?
            """,
            (
                state.value,
                account_id,
                error_code,
                error_message,
                job_member_id,
                JobMemberState.PROCESSING.value,
            ),
        )
        if cursor.rowcount != 1:
            self.connection.rollback()
            raise ValueError("Job member must be PROCESSING before terminal completion")
        self.connection.commit()

    def schedule_retry(
        self,
        job_member_id: int,
        retry_seconds: int,
        *,
        account_id: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        cursor = self.connection.execute(
            """
            UPDATE job_members SET state = ?, lease_owner = NULL, lease_until = NULL,
                next_retry_at = ?, last_account_id = ?, last_error_code = ?, last_error_message = ?,
                attempt_count = attempt_count + 1, updated_at = datetime('now')
            WHERE id = ? AND state = ?
            """,
            (
                JobMemberState.RETRY_WAIT.value,
                _sqlite_after(retry_seconds),
                account_id,
                error_code,
                error_message,
                job_member_id,
                JobMemberState.PROCESSING.value,
            ),
        )
        if cursor.rowcount != 1:
            self.connection.rollback()
            raise ValueError("Job member must be PROCESSING before retry scheduling")
        self.connection.commit()

    def release_due_retries(self) -> int:
        cursor = self.connection.execute(
            """
            UPDATE job_members SET state = ?, next_retry_at = NULL, updated_at = datetime('now')
            WHERE state = ? AND next_retry_at <= datetime('now')
            """,
            (JobMemberState.READY.value, JobMemberState.RETRY_WAIT.value),
        )
        self.connection.commit()
        return int(cursor.rowcount)

    def release_processing(
        self,
        job_member_id: int,
        *,
        increment_attempt: bool = False,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        increment = 1 if increment_attempt else 0
        self.connection.execute(
            """
            UPDATE job_members SET state = ?, lease_owner = NULL, lease_until = NULL,
                attempt_count = attempt_count + ?, last_error_code = ?, last_error_message = ?,
                updated_at = datetime('now') WHERE id = ? AND state = ?
            """,
            (
                JobMemberState.READY.value,
                increment,
                error_code,
                error_message,
                job_member_id,
                JobMemberState.PROCESSING.value,
            ),
        )
        self.connection.commit()

    def expired_processing(self) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT jm.id, jm.job_id, jm.member_id, jm.attempt_count,
                   m.telegram_user_id, m.access_hash, m.username
            FROM job_members jm
            JOIN members m ON m.id = jm.member_id
            WHERE jm.state = ? AND jm.lease_until IS NOT NULL
              AND jm.lease_until <= datetime('now')
            ORDER BY jm.id
            """,
            (JobMemberState.PROCESSING.value,),
        ).fetchall()

    def count_state(self, job_id: int, state: JobMemberState) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) FROM job_members WHERE job_id = ? AND state = ?",
            (job_id, state.value),
        ).fetchone()
        return int(row[0]) if row else 0

    def is_terminal(self, job_id: int) -> bool:
        row = self.connection.execute(
            """
            SELECT COUNT(*) FROM job_members
            WHERE job_id = ? AND state IN ('READY','PROCESSING','RETRY_WAIT','CANDIDATE')
            """,
            (job_id,),
        ).fetchone()
        return int(row[0]) == 0
