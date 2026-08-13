from __future__ import annotations

import sqlite3
from pathlib import Path

from .migration_manager import MigrationManager


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.connection: sqlite3.Connection | None = None

    def open(self) -> sqlite3.Connection:
        if self.connection is not None:
            return self.connection
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        self.connection = connection
        return connection

    def migrate(self) -> list[int]:
        connection = self.open()
        migrations_dir = Path(__file__).with_name("migrations")
        return MigrationManager(connection, migrations_dir).apply_all()

    def quick_check(self) -> str:
        connection = self.open()
        row = connection.execute("PRAGMA quick_check").fetchone()
        return str(row[0]) if row else "unknown"

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __enter__(self) -> Database:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
