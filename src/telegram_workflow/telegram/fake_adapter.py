from __future__ import annotations

from collections.abc import AsyncIterator

from telegram_workflow.domain.enums import AttemptResult, ErrorScope, JobMemberState
from telegram_workflow.domain.models import ActionOutcome, TelegramMember
from telegram_workflow.telegram.adapter import (
    AuthorizedActionAdapter,
    ResolvedEntity,
    TargetValidation,
    TelegramAdapter,
)


class FakeTelegramAdapter(TelegramAdapter, AuthorizedActionAdapter):
    def __init__(
        self,
        members: list[TelegramMember] | None = None,
        outcomes: dict[int, ActionOutcome] | None = None,
        verification: dict[int, bool | None] | None = None,
    ) -> None:
        self.members = members or []
        self.outcomes = outcomes or {}
        self.verification = verification or {}

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

    async def perform_authorized_action(
        self,
        *,
        target: ResolvedEntity,
        member: TelegramMember,
        account_id: int | None,
    ) -> ActionOutcome:
        del target, account_id
        return self.outcomes.get(
            member.user_id,
            ActionOutcome(
                result=AttemptResult.SUCCESS,
                code="FAKE_SUCCESS",
                scope=ErrorScope.MEMBER,
                final_state=JobMemberState.SUCCESS,
            ),
        )

    async def verify_authorized_action(
        self,
        *,
        target: ResolvedEntity,
        member: TelegramMember,
    ) -> bool | None:
        del target
        return self.verification.get(member.user_id)
