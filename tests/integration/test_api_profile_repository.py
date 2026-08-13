from pathlib import Path

from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.api_profiles import ApiProfileRepository


def test_api_profile_stores_secret_reference_not_secret_value(tmp_path: Path) -> None:
    with Database(tmp_path / "app.db") as database:
        database.migrate()
        repo = ApiProfileRepository(database.open())
        profile_id = repo.upsert(name="main", api_id=12345, api_hash_secret_ref="api/main/hash")
        row = repo.get(profile_id)
        assert row is not None
        assert row["api_id"] == 12345
        assert row["api_hash_secret_ref"] == "api/main/hash"
