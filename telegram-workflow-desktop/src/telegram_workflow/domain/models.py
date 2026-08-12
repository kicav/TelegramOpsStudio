from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TelegramMember:
    user_id: int
    access_hash: int | None = None
    username: str | None = None
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    is_bot: bool = False
    is_deleted: bool = False
    last_seen: str | None = None
