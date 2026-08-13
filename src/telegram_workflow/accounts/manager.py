from __future__ import annotations

from pathlib import Path

from telegram_workflow.domain.enums import AccountState
from telegram_workflow.storage.repositories.accounts import AccountRepository
from telegram_workflow.telegram.telethon_adapter import TelethonReadOnlyAdapter


class AccountManager:
    def __init__(self, connection) -> None:
        self.accounts = AccountRepository(connection)

    def register(self, *, phone: str, session_path: Path, api_profile_id: int | None = None) -> int:
        return self.accounts.add(phone, str(session_path), api_profile_id)

    async def check_session(
        self,
        *,
        account_id: int,
        session_path: Path,
        api_id: int,
        api_hash: str,
    ) -> bool:
        adapter = TelethonReadOnlyAdapter(
            session_path=session_path,
            api_id=api_id,
            api_hash=api_hash,
        )
        try:
            healthy = await adapter.health_check()
        except Exception:
            self.accounts.set_state(account_id, AccountState.INVALID_SESSION)
            return False
        finally:
            await adapter.close()
        self.accounts.set_state(
            account_id, AccountState.READY if healthy else AccountState.AUTH_REQUIRED
        )
        return healthy
