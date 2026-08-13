from pathlib import Path

from telegram_workflow.domain.models import AuditEntry
from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.audit import AuditRepository
from telegram_workflow.storage.repositories.settings import SettingsRepository


def test_settings_and_audit_are_persistent(tmp_path: Path) -> None:
    with Database(tmp_path / "app.db") as database:
        database.migrate()
        connection = database.open()
        settings = SettingsRepository(connection)
        settings.set("ui.language", {"value": "vi"})
        assert settings.get("ui.language") == {"value": "vi"}

        audit = AuditRepository(connection)
        audit.append(AuditEntry("JOB_CREATED", "job", "7", {"source": 1}))
        row = audit.recent(1)[0]
        assert row["event_type"] == "JOB_CREATED"
        assert row["entity_id"] == "7"
