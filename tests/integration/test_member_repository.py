from pathlib import Path

from telegram_workflow.domain.models import TelegramMember
from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.members import MemberRepository


def test_member_upsert_deduplicates_by_telegram_user_id(tmp_path: Path) -> None:
    with Database(tmp_path / "app.db") as database:
        database.migrate()
        repo = MemberRepository(database.open())
        repo.upsert_many([TelegramMember(user_id=1, username="old", access_hash=10)])
        repo.upsert_many([TelegramMember(user_id=1, username="new", access_hash=None)])

        rows = database.open().execute(
            "SELECT telegram_user_id, username, access_hash FROM members"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["telegram_user_id"] == 1
        assert rows[0]["username"] == "new"
        assert rows[0]["access_hash"] == 10
