from __future__ import annotations

from abc import ABC, abstractmethod


class SecretStore(ABC):
    @abstractmethod
    def get(self, reference: str) -> str | None: ...

    @abstractmethod
    def set(self, reference: str, value: str) -> None: ...

    @abstractmethod
    def delete(self, reference: str) -> None: ...


class MemorySecretStore(SecretStore):
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get(self, reference: str) -> str | None:
        return self._values.get(reference)

    def set(self, reference: str, value: str) -> None:
        self._values[reference] = value

    def delete(self, reference: str) -> None:
        self._values.pop(reference, None)


class KeyringSecretStore(SecretStore):
    """Uses the operating system credential backend through the keyring package."""

    def __init__(self, service_name: str = "TelegramOpsStudio") -> None:
        self.service_name = service_name

    def _keyring(self):
        try:
            import keyring
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("keyring is not installed") from exc
        return keyring

    def get(self, reference: str) -> str | None:
        return self._keyring().get_password(self.service_name, reference)

    def set(self, reference: str, value: str) -> None:
        self._keyring().set_password(self.service_name, reference, value)

    def delete(self, reference: str) -> None:
        try:
            self._keyring().delete_password(self.service_name, reference)
        except Exception:
            return None
