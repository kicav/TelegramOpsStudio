from pathlib import Path

from telegram_workflow.domain.models import TelegramMember
from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.members import MemberRepository


def test_member_consent_migration_and_filtering(tmp_path: Path) -> None:
    with Database(tmp_path / "app.db") as database:
        applied = database.migrate()
        assert 2 in applied
        repo = MemberRepository(database.open())
        repo.upsert_many(
            [
                TelegramMember(user_id=101, username="alpha", first_name="Alpha"),
                TelegramMember(user_id=102, username="beta", first_name="Beta"),
            ]
        )
        ids = repo.ids_for_user_ids([101, 102])
        assert repo.set_consent([ids[101]], "OPTED_IN", notes="form") == 1
        rows, total = repo.list_rows(consent_state="OPTED_IN")
        assert total == 1
        assert rows[0]["telegram_user_id"] == 101
        assert rows[0]["consent_state"] == "OPTED_IN"
        assert rows[0]["notes"] == "form"


def test_member_catalog_search(tmp_path: Path) -> None:
    with Database(tmp_path / "app.db") as database:
        database.migrate()
        repo = MemberRepository(database.open())
        repo.upsert_many(
            [
                TelegramMember(user_id=201, username="robotics_lab", first_name="Tam"),
                TelegramMember(user_id=202, username="other", first_name="An"),
            ]
        )
        rows, total = repo.list_rows(search="robotics")
        assert total == 1
        assert rows[0]["telegram_user_id"] == 201
