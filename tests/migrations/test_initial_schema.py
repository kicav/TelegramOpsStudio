from pathlib import Path

from telegram_workflow.storage.database import Database

EXPECTED_TABLES = {
    "schema_migrations",
    "api_profiles",
    "accounts",
    "members",
    "sources",
    "source_members",
    "targets",
    "target_snapshots",
    "target_snapshot_members",
    "jobs",
    "job_members",
    "attempts",
    "audit_log",
    "settings",
}


def test_initial_migration_creates_expected_tables(tmp_path: Path) -> None:
    with Database(tmp_path / "app.db") as database:
        assert database.migrate() == [1, 2]
        connection = database.open()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert EXPECTED_TABLES <= tables
        assert database.quick_check() == "ok"


def test_migration_is_idempotent(tmp_path: Path) -> None:
    with Database(tmp_path / "app.db") as database:
        database.migrate()
        assert database.migrate() == []
