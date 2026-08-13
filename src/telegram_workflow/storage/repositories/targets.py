from __future__ import annotations

import sqlite3

from telegram_workflow.domain.enums import SnapshotState, TargetValidationState
from telegram_workflow.telegram.adapter import ResolvedEntity, TargetValidation


class TargetRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create(self, identifier: str) -> int:
        cursor = self.connection.execute(
            "INSERT INTO targets(input_identifier) VALUES (?)", (identifier,)
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def set_resolved(self, target_id: int, entity: ResolvedEntity) -> None:
        self.connection.execute(
            """
            UPDATE targets SET telegram_entity_id = ?, title = ?, username = ?, entity_type = ?,
                validation_state = ?, validation_error = NULL, updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                entity.entity_id,
                entity.title,
                entity.username,
                entity.entity_type,
                TargetValidationState.RESOLVING.value,
                target_id,
            ),
        )
        self.connection.commit()

    def set_validation(self, target_id: int, validation: TargetValidation) -> None:
        state = TargetValidationState.READY if validation.ready else TargetValidationState.REJECTED
        self.connection.execute(
            """
            UPDATE targets SET validation_state = ?, permission_state = ?, validation_error = ?,
                last_validated = datetime('now'), updated_at = datetime('now') WHERE id = ?
            """,
            (state.value, validation.permission_state, validation.reason, target_id),
        )
        self.connection.commit()


class TargetSnapshotRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create(self, target_id: int, state: SnapshotState = SnapshotState.NEW) -> int:
        cursor = self.connection.execute(
            "INSERT INTO target_snapshots(target_id, snapshot_state) VALUES (?, ?)",
            (target_id, state.value),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def add_members(self, snapshot_id: int, member_ids: list[int]) -> int:
        if not member_ids:
            return 0
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO target_snapshot_members(snapshot_id, member_id)
            VALUES (?, ?)
            """,
            [(snapshot_id, member_id) for member_id in member_ids],
        )
        self.connection.commit()
        return len(member_ids)

    def finalize(self, snapshot_id: int) -> None:
        row = self.connection.execute(
            "SELECT COUNT(*) FROM target_snapshot_members WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        member_count = int(row[0]) if row else 0
        self.connection.execute(
            """
            UPDATE target_snapshots SET snapshot_state = ?, captured_at = datetime('now'),
                member_count = ?, error_message = NULL WHERE id = ?
            """,
            (SnapshotState.COMPLETE.value, member_count, snapshot_id),
        )
        self.connection.commit()

    def replace_members(self, snapshot_id: int, member_ids: list[int]) -> None:
        self.connection.execute(
            "DELETE FROM target_snapshot_members WHERE snapshot_id = ?", (snapshot_id,)
        )
        self.connection.executemany(
            "INSERT INTO target_snapshot_members(snapshot_id, member_id) VALUES (?, ?)",
            [(snapshot_id, member_id) for member_id in member_ids],
        )
        self.connection.execute(
            """
            UPDATE target_snapshots SET snapshot_state = ?, captured_at = datetime('now'),
                member_count = ?, error_message = NULL WHERE id = ?
            """,
            (SnapshotState.COMPLETE.value, len(member_ids), snapshot_id),
        )
        self.connection.commit()

    def mark_unavailable(self, snapshot_id: int, reason: str) -> None:
        self.connection.execute(
            """
            UPDATE target_snapshots SET snapshot_state = ?, captured_at = datetime('now'),
                error_message = ? WHERE id = ?
            """,
            (SnapshotState.UNAVAILABLE.value, reason, snapshot_id),
        )
        self.connection.commit()

    def member_ids(self, snapshot_id: int | None) -> set[int]:
        if snapshot_id is None:
            return set()
        rows = self.connection.execute(
            "SELECT member_id FROM target_snapshot_members WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchall()
        return {int(row["member_id"]) for row in rows}
