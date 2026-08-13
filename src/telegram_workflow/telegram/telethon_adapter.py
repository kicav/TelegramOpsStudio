from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from telegram_workflow.domain.enums import ActivityQuality
from telegram_workflow.domain.models import TelegramMember
from telegram_workflow.telegram.adapter import ResolvedEntity, TargetValidation, TelegramAdapter


class TelethonReadOnlyAdapter(TelegramAdapter):
    """Read-only Telethon adapter for health, resolution, scans and permission checks."""

    def __init__(self, *, session_path: Path, api_id: int, api_hash: str) -> None:
        self.session_path = Path(session_path)
        self.api_id = api_id
        self.api_hash = api_hash
        self._client: Any | None = None
        self._entities: dict[int, Any] = {}

    def _new_client(self) -> Any:
        try:
            from telethon import TelegramClient
        except ImportError as exc:  # pragma: no cover - depends on optional runtime package
            raise RuntimeError("Telethon is not installed") from exc
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        return TelegramClient(str(self.session_path), self.api_id, self.api_hash)

    async def _client_ready(self) -> Any:
        if self._client is None:
            self._client = self._new_client()
        if not self._client.is_connected():
            await self._client.connect()
        return self._client

    async def health_check(self) -> bool:
        client = await self._client_ready()
        return bool(await client.is_user_authorized())

    async def resolve_entity(self, identifier: str) -> ResolvedEntity:
        client = await self._client_ready()
        raw = await client.get_entity(identifier)
        try:
            from telethon import utils

            entity_id = int(utils.get_peer_id(raw))
        except Exception:
            entity_id = int(getattr(raw, "id"))
        title = str(
            getattr(raw, "title", None)
            or " ".join(
                part
                for part in (getattr(raw, "first_name", None), getattr(raw, "last_name", None))
                if part
            )
            or entity_id
        )
        resolved = ResolvedEntity(
            entity_id=entity_id,
            title=title,
            username=getattr(raw, "username", None),
            entity_type=type(raw).__name__,
        )
        self._entities[entity_id] = raw
        return resolved

    async def iter_accessible_members(
        self, entity: ResolvedEntity
    ) -> AsyncIterator[TelegramMember]:
        client = await self._client_ready()
        raw = self._entities.get(entity.entity_id)
        if raw is None:
            raw = await client.get_entity(entity.entity_id)
        async for user in client.iter_participants(raw):
            status = getattr(user, "status", None)
            last_seen = getattr(status, "was_online", None)
            quality = ActivityQuality.KNOWN if last_seen is not None else ActivityQuality.UNKNOWN
            yield TelegramMember(
                user_id=int(user.id),
                access_hash=getattr(user, "access_hash", None),
                username=getattr(user, "username", None),
                first_name=getattr(user, "first_name", None) or "",
                last_name=getattr(user, "last_name", None) or "",
                phone=getattr(user, "phone", None) or "",
                is_bot=bool(getattr(user, "bot", False)),
                is_deleted=bool(getattr(user, "deleted", False)),
                last_seen=last_seen.isoformat() if last_seen is not None else None,
                activity_quality=quality,
            )

    async def validate_target(self, entity: ResolvedEntity) -> TargetValidation:
        client = await self._client_ready()
        raw = self._entities.get(entity.entity_id)
        if raw is None:
            raw = await client.get_entity(entity.entity_id)
        try:
            permissions = await client.get_permissions(raw, "me")
        except Exception as exc:
            return TargetValidation(False, "UNAVAILABLE", f"{type(exc).__name__}: {exc}")
        if permissions is None:
            return TargetValidation(False, "UNKNOWN", "Target permissions could not be determined")
        can_invite = bool(
            getattr(permissions, "is_creator", False)
            or getattr(permissions, "is_admin", False)
            and getattr(permissions, "invite_users", False)
        )
        return TargetValidation(
            ready=can_invite,
            permission_state="INVITE_ALLOWED" if can_invite else "INVITE_NOT_ALLOWED",
            reason=None if can_invite else "Authenticated account lacks invite permission",
        )

    async def close(self) -> None:
        if self._client is not None and self._client.is_connected():
            await self._client.disconnect()
        self._client = None
        self._entities.clear()
