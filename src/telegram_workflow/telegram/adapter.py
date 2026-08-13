from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from telegram_workflow.domain.models import ActionOutcome, TelegramMember


@dataclass(frozen=True, slots=True)
class ResolvedEntity:
    entity_id: int
    title: str
    username: str | None
    entity_type: str


@dataclass(frozen=True, slots=True)
class TargetValidation:
    ready: bool
    permission_state: str
    reason: str | None = None


class TelegramAdapter(ABC):
    """Read/validation boundary for Telegram access.

    Implementations may only enumerate member lists that Telegram actually exposes to
    the authenticated account. No fallback based on message-sender scraping belongs here.
    """

    @abstractmethod
    async def health_check(self) -> bool: ...

    @abstractmethod
    async def resolve_entity(self, identifier: str) -> ResolvedEntity: ...

    @abstractmethod
    async def iter_accessible_members(
        self, entity: ResolvedEntity
    ) -> AsyncIterator[TelegramMember]: ...

    @abstractmethod
    async def validate_target(self, entity: ResolvedEntity) -> TargetValidation: ...

    async def close(self) -> None:
        return None


class AuthorizedActionAdapter(ABC):
    """Test/admin-authorized side-effect boundary.

    CI uses a fake implementation. The production Telethon adapter in this project is
    intentionally read-only; no bulk membership action is wired into it.
    """

    @abstractmethod
    async def perform_authorized_action(
        self,
        *,
        target: ResolvedEntity,
        member: TelegramMember,
        account_id: int | None,
    ) -> ActionOutcome: ...

    @abstractmethod
    async def verify_authorized_action(
        self,
        *,
        target: ResolvedEntity,
        member: TelegramMember,
    ) -> bool | None: ...
