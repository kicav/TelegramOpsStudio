from __future__ import annotations

import json
import sqlite3

from telegram_workflow.domain.models import AuditEntry


class AuditRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def append(self, entry: AuditEntry) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO audit_log(event_type, entity_type, entity_id, details_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                entry.event_type,
                entry.entity_type,
                entry.entity_id,
                json.dumps(entry.details, ensure_ascii=False, sort_keys=True),
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def recent(self, limit: int = 100) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
