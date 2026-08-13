from pathlib import Path

from telegram_workflow.accounts.scheduler import AccountScheduler
from telegram_workflow.domain.enums import AccountState
from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.accounts import AccountRepository


def test_scheduler_uses_only_ready_selected_accounts(tmp_path: Path) -> None:
    with Database(tmp_path / "app.db") as database:
        database.migrate()
        connection = database.open()
        accounts = AccountRepository(connection)
        one = accounts.add("+1001")
        two = accounts.add("+1002")
        three = accounts.add("+1003")
        accounts.set_state(one, AccountState.READY)
        accounts.set_state(two, AccountState.COOLDOWN)
        accounts.set_state(three, AccountState.READY)

        scheduler = AccountScheduler(connection, selected_account_ids=[two, three])
        assert scheduler.next_ready() == three
        assert scheduler.next_ready() == three
