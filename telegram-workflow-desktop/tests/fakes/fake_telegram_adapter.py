from __future__ import annotations

from collections.abc import AsyncIterator

from telegram_workflow.domain.models import TelegramMember
from telegram_workflow.telegram.adapter import ResolvedEntity, TargetValidation, TelegramAdapter


class FakeTelegramAdapter(TelegramAdapter):
    def __init__(self, members: list[TelegramMember] | None = None) -> None:
        self.members = members or []

    async def health_check(self) -> bool:
        return True

    async def resolve_entity(self, identifier: str) -> ResolvedEntity:
        return ResolvedEntity(
            entity_id=abs(hash(identifier)) % 10_000_000,
            title=f"Fake: {identifier}",
            username=None,
            entity_type="fake_group",
        )

    async def iter_accessible_members(
        self, entity: ResolvedEntity
    ) -> AsyncIterator[TelegramMember]:
        del entity
        for member in self.members:
            yield member

    async def validate_target(self, entity: ResolvedEntity) -> TargetValidation:
        del entity
        return TargetValidation(ready=True, permission_state="FAKE_ALLOWED")
