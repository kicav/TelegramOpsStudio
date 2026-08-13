import sqlite3
from pathlib import Path

import pytest

from telegram_workflow.domain.errors import DatabaseMigrationError
from telegram_workflow.storage.migration_manager import MigrationManager


def test_failed_migration_rolls_back_schema_and_version(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_good.sql").write_text(
        "CREATE TABLE good_table(id INTEGER PRIMARY KEY);", encoding="utf-8"
    )
    (migrations / "0002_bad.sql").write_text(
        "CREATE TABLE should_rollback(id INTEGER); THIS IS NOT SQL;", encoding="utf-8"
    )

    connection = sqlite3.connect(tmp_path / "app.db")
    manager = MigrationManager(connection, migrations)

    with pytest.raises(DatabaseMigrationError):
        manager.apply_all()

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    versions = {
        row[0] for row in connection.execute("SELECT version FROM schema_migrations")
    }
    connection.close()

    assert "good_table" in tables
    assert "should_rollback" not in tables
    assert versions == {1}
