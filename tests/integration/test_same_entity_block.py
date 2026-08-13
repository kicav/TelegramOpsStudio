from pathlib import Path

import pytest

from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.jobs import JobRepository
from telegram_workflow.storage.repositories.sources import SourceRepository
from telegram_workflow.storage.repositories.targets import TargetRepository
from telegram_workflow.telegram.adapter import ResolvedEntity


def test_source_and_target_same_telegram_entity_is_blocked(tmp_path: Path) -> None:
    with Database(tmp_path / "app.db") as database:
        database.migrate()
        connection = database.open()
        source_id = SourceRepository(connection).create("source")
        target_id = TargetRepository(connection).create("target")
        entity = ResolvedEntity(444, "Same", None, "group")
        SourceRepository(connection).set_resolved(source_id, entity)
        TargetRepository(connection).set_resolved(target_id, entity)

        with pytest.raises(ValueError, match="same Telegram entity"):
            JobRepository(connection).create(
                name="invalid",
                source_id=source_id,
                target_id=target_id,
                target_snapshot_id=None,
                filter_snapshot={},
            )
