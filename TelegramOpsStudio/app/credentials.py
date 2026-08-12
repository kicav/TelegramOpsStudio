from __future__ import annotations

import keyring
from keyring.errors import KeyringError, NoKeyringError, PasswordDeleteError

SERVICE = "TelegramOpsStudio"


def _api_key(phone: str) -> str:
    return f"account:{phone}:api_hash"


def _proxy_key(proxy_id: int) -> str:
    return f"proxy:{proxy_id}:password"


def _set(name: str, value: str) -> None:
    try:
        keyring.set_password(SERVICE, name, value)
    except (NoKeyringError, KeyringError) as exc:
        raise RuntimeError(
            "No usable OS credential store is available. On Windows, ensure Windows Credential Manager is enabled."
        ) from exc


def _get(name: str) -> str | None:
    try:
        return keyring.get_password(SERVICE, name)
    except (NoKeyringError, KeyringError) as exc:
        raise RuntimeError(
            "No usable OS credential store is available. On Windows, ensure Windows Credential Manager is enabled."
        ) from exc


def _delete(name: str) -> None:
    try:
        keyring.delete_password(SERVICE, name)
    except PasswordDeleteError:
        pass
    except (NoKeyringError, KeyringError) as exc:
        raise RuntimeError("Could not access the OS credential store") from exc


def set_api_hash(phone: str, api_hash: str) -> None:
    _set(_api_key(phone), api_hash)


def get_api_hash(phone: str) -> str | None:
    return _get(_api_key(phone))


def delete_api_hash(phone: str) -> None:
    _delete(_api_key(phone))


def set_proxy_password(proxy_id: int, password: str) -> None:
    if password:
        _set(_proxy_key(proxy_id), password)
        return
    # A proxy without authentication does not require a credential backend.
    try:
        delete_proxy_password(proxy_id)
    except RuntimeError:
        pass


def get_proxy_password(proxy_id: int) -> str | None:
    return _get(_proxy_key(proxy_id))


def delete_proxy_password(proxy_id: int) -> None:
    _delete(_proxy_key(proxy_id))
