from pathlib import Path

from telegram_workflow.domain.enums import AccountState
from telegram_workflow.domain.models import TelegramMember
from telegram_workflow.exports.exporter import ResultExporter
from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.accounts import AccountRepository
from telegram_workflow.storage.repositories.api_profiles import ApiProfileRepository
from telegram_workflow.storage.repositories.members import MemberRepository


def test_account_listing_includes_api_profile(tmp_path: Path) -> None:
    with Database(tmp_path / "app.db") as database:
        database.migrate()
        connection = database.open()
        profiles = ApiProfileRepository(connection)
        profile_id = profiles.upsert(
            name="Default", api_id=12345, api_hash_secret_ref="secret-ref"
        )
        accounts = AccountRepository(connection)
        account_id = accounts.add(
            "+84123456789", str(tmp_path / "session"), profile_id
        )
        accounts.set_state(account_id, AccountState.READY)

        row = accounts.get_with_profile(account_id)
        assert row is not None
        assert row["api_profile_name"] == "Default"
        assert row["api_id"] == 12345
        assert row["api_hash_secret_ref"] == "secret-ref"
        assert accounts.list_all()[0]["state"] == AccountState.READY.value


def test_member_export_chunks_large_selection(tmp_path: Path) -> None:
    with Database(tmp_path / "app.db") as database:
        database.migrate()
        connection = database.open()
        members = MemberRepository(connection)
        payload = [
            TelegramMember(user_id=1_000_000 + index, username=f"u{index}")
            for index in range(1_205)
        ]
        members.upsert_many(payload)
        mapping = members.ids_for_user_ids([item.user_id for item in payload])
        member_ids = [mapping[item.user_id] for item in payload]

        path = tmp_path / "members.csv"
        exported = ResultExporter(connection).export_members_csv(member_ids, path)

        assert exported == len(payload)
        assert path.exists()
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        assert len(lines) == len(payload) + 1
        assert "User ID" in lines[0]
