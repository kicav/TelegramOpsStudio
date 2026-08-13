from pathlib import Path

from telegram_workflow.domain.enums import ActivityQuality
from telegram_workflow.domain.models import FilterConfig, TelegramMember
from telegram_workflow.filters.engine import FilterEngine
from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.members import MemberRepository


def test_unknown_activity_is_not_silently_treated_as_offline(tmp_path: Path) -> None:
    with Database(tmp_path / "app.db") as database:
        database.migrate()
        connection = database.open()
        MemberRepository(connection).upsert_many(
            [TelegramMember(user_id=1, activity_quality=ActivityQuality.UNKNOWN)]
        )
        row = connection.execute("SELECT * FROM members WHERE telegram_user_id = 1").fetchone()
        engine = FilterEngine()
        assert engine.eligible(row, FilterConfig(allow_unknown_activity=True)) is True
        assert engine.eligible(row, FilterConfig(allow_unknown_activity=False)) is False
