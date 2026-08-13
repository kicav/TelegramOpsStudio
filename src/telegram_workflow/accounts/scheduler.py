from __future__ import annotations

from collections import deque

from telegram_workflow.storage.repositories.accounts import AccountRepository


class AccountScheduler:
    """Selects only READY accounts; it never rotates around restrictions to evade server limits."""

    def __init__(self, connection, selected_account_ids: list[int] | None = None) -> None:
        ready = AccountRepository(connection).ready_ids()
        if selected_account_ids is not None:
            allowed = set(selected_account_ids)
            ready = [account_id for account_id in ready if account_id in allowed]
        self._pool = deque(ready)

    def next_ready(self) -> int | None:
        if not self._pool:
            return None
        account_id = self._pool[0]
        self._pool.rotate(-1)
        return account_id
