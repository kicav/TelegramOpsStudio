from __future__ import annotations

from pathlib import Path
from typing import Any


class TelethonAuthService:
    """Interactive session login helper. OTP and 2FA values are never persisted by this class."""

    def __init__(self, *, session_path: Path, api_id: int, api_hash: str) -> None:
        self.session_path = Path(session_path)
        self.api_id = api_id
        self.api_hash = api_hash
        self._client: Any | None = None

    async def connect(self) -> None:
        try:
            from telethon import TelegramClient
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Telethon is not installed") from exc
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self._client = TelegramClient(str(self.session_path), self.api_id, self.api_hash)
        await self._client.connect()

    async def is_authorized(self) -> bool:
        if self._client is None:
            await self.connect()
        return bool(await self._client.is_user_authorized())

    async def request_code(self, phone: str) -> str:
        if self._client is None:
            await self.connect()
        sent = await self._client.send_code_request(phone)
        return str(sent.phone_code_hash)

    async def sign_in_code(self, *, phone: str, code: str, phone_code_hash: str) -> bool:
        if self._client is None:
            await self.connect()
        try:
            await self._client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except Exception as exc:
            if type(exc).__name__ == "SessionPasswordNeededError":
                return False
            raise
        return True

    async def sign_in_password(self, password: str) -> None:
        if self._client is None:
            await self.connect()
        await self._client.sign_in(password=password)

    async def close(self) -> None:
        if self._client is not None and self._client.is_connected():
            await self._client.disconnect()
        self._client = None
