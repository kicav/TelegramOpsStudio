import asyncio
from pathlib import Path

from telegram_workflow.domain.models import TelegramMember
from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.sources import SourceRepository
from telegram_workflow.telegram.source_scanner import SourceScanner
from tests.fakes.fake_telegram_adapter import FakeTelegramAdapter


def test_source_scanner_persists_in_batches_and_deduplicates(tmp_path: Path) -> None:
    async def scenario() -> None:
        members = [
            TelegramMember(user_id=1, username="one"),
            TelegramMember(user_id=2, username="two"),
            TelegramMember(user_id=2, username="two-new"),
            TelegramMember(user_id=3, username="three"),
        ]
        with Database(tmp_path / "app.db") as database:
            database.migrate()
            connection = database.open()
            sources = SourceRepository(connection)
            source_id = sources.create("source")
            scanner = SourceScanner(connection, FakeTelegramAdapter(members))
            total = await scanner.scan(source_id=source_id, identifier="source", batch_size=2)
            assert total == 3
            assert sources.count_members(source_id) == 3
            row = connection.execute(
                "SELECT username FROM members WHERE telegram_user_id = 2"
            ).fetchone()
            assert row["username"] == "two-new"

    asyncio.run(scenario())
