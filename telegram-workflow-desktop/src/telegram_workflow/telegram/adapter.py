from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from telegram_workflow.domain.models import TelegramMember


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
    """Boundary for Telegram access. CI uses a fake implementation only."""

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
