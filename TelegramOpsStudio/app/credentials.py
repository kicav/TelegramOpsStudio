from __future__ import annotations

import keyring

SERVICE = "TelegramOpsStudio"


def _key(phone: str, field: str) -> str:
    return f"{phone}:{field}"


def set_api_hash(phone: str, api_hash: str) -> None:
    keyring.set_password(SERVICE, _key(phone, "api_hash"), api_hash)


def get_api_hash(phone: str) -> str | None:
    return keyring.get_password(SERVICE, _key(phone, "api_hash"))


def delete_api_hash(phone: str) -> None:
    try:
        keyring.delete_password(SERVICE, _key(phone, "api_hash"))
    except keyring.errors.PasswordDeleteError:
        pass
