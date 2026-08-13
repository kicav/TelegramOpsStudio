from __future__ import annotations

from dataclasses import dataclass

from telegram_workflow.domain.enums import AccountState


@dataclass(frozen=True, slots=True)
class AccountHealth:
    account_id: int
    state: AccountState
    detail: str = ""
