from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from telegram_workflow.domain.errors import DatabaseMigrationError

_MIGRATION_RE = re.compile(r"^(?P<version>\d+)_.*\.sql$")


class MigrationManager:
    def __init__(self, connection: sqlite3.Connection, migrations_dir: Path) -> None:
        self.connection = connection
        self.migrations_dir = migrations_dir

    def _available(self) -> list[tuple[int, Path]]:
        result: list[tuple[int, Path]] = []
        for path in sorted(self.migrations_dir.glob("*.sql")):
            match = _MIGRATION_RE.match(path.name)
            if match:
                result.append((int(match.group("version")), path))
        return result

    def apply_all(self) -> list[int]:
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, "
            "applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        self.connection.commit()
        applied = {
            int(row[0])
            for row in self.connection.execute("SELECT version FROM schema_migrations")
        }
        newly_applied: list[int] = []

        for version, path in self._available():
            if version in applied:
                continue
            script = path.read_text(encoding="utf-8")
            escaped_version = int(version)
            atomic_script = (
                "BEGIN IMMEDIATE;\n"
                f"{script}\n"
                "INSERT INTO schema_migrations(version) "
                f"VALUES ({escaped_version});\n"
                "COMMIT;\n"
            )
            try:
                self.connection.executescript(atomic_script)
            except sqlite3.DatabaseError as exc:
                if self.connection.in_transaction:
                    self.connection.rollback()
                raise DatabaseMigrationError(
                    f"Failed migration {version} ({path.name}): {exc}"
                ) from exc
            newly_applied.append(version)
        return newly_applied
