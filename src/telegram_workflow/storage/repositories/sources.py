from __future__ import annotations

import sqlite3

from telegram_workflow.domain.enums import SourceState
from telegram_workflow.telegram.adapter import ResolvedEntity


class SourceRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create(self, identifier: str) -> int:
        cursor = self.connection.execute(
            "INSERT INTO sources(input_identifier) VALUES (?)", (identifier,)
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def set_resolved(self, source_id: int, entity: ResolvedEntity) -> None:
        self.connection.execute(
            """
            UPDATE sources
            SET telegram_entity_id = ?, title = ?, username = ?, entity_type = ?,
                scan_state = ?, scan_error = NULL, updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                entity.entity_id,
                entity.title,
                entity.username,
                entity.entity_type,
                SourceState.READY.value,
                source_id,
            ),
        )
        self.connection.commit()

    def set_scan_state(
        self,
        source_id: int,
        state: SourceState,
        *,
        scanned_count: int | None = None,
        error: str | None = None,
    ) -> None:
        if state == SourceState.SCANNING:
            self.connection.execute(
                """
                UPDATE sources SET scan_state = ?, last_scan_started = datetime('now'),
                    scan_error = NULL, updated_at = datetime('now') WHERE id = ?
                """,
                (state.value, source_id),
            )
        elif state in {SourceState.COMPLETE, SourceState.PARTIAL, SourceState.FAILED}:
            self.connection.execute(
                """
                UPDATE sources SET scan_state = ?, last_scan_finished = datetime('now'),
                    scanned_member_count = COALESCE(?, scanned_member_count), scan_error = ?,
                    updated_at = datetime('now') WHERE id = ?
                """,
                (state.value, scanned_count, error, source_id),
            )
        else:
            self.connection.execute(
                "UPDATE sources SET scan_state = ?, updated_at = datetime('now') WHERE id = ?",
                (state.value, source_id),
            )
        self.connection.commit()

    def link_members(self, source_id: int, member_ids: list[int]) -> int:
        if not member_ids:
            return 0
        self.connection.executemany(
            """
            INSERT INTO source_members(source_id, member_id)
            VALUES (?, ?)
            ON CONFLICT(source_id, member_id) DO UPDATE SET
                last_seen_in_source = datetime('now')
            """,
            [(source_id, member_id) for member_id in member_ids],
        )
        self.connection.commit()
        return len(member_ids)

    def member_rows(self, source_id: int) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT m.* FROM members m
            JOIN source_members sm ON sm.member_id = m.id
            WHERE sm.source_id = ?
            ORDER BY m.id
            """,
            (source_id,),
        ).fetchall()

    def count_members(self, source_id: int) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) FROM source_members WHERE source_id = ?", (source_id,)
        ).fetchone()
        return int(row[0]) if row else 0
