from __future__ import annotations

from telegram_workflow.domain.enums import SnapshotState
from telegram_workflow.domain.models import TelegramMember
from telegram_workflow.storage.repositories.members import MemberRepository
from telegram_workflow.storage.repositories.targets import (
    TargetRepository,
    TargetSnapshotRepository,
)
from telegram_workflow.telegram.adapter import ResolvedEntity, TargetValidation, TelegramAdapter


class TargetValidator:
    def __init__(self, connection, adapter: TelegramAdapter) -> None:
        self.members = MemberRepository(connection)
        self.targets = TargetRepository(connection)
        self.snapshots = TargetSnapshotRepository(connection)
        self.adapter = adapter

    async def validate(
        self, *, target_id: int, identifier: str
    ) -> tuple[ResolvedEntity, TargetValidation]:
        entity = await self.adapter.resolve_entity(identifier)
        self.targets.set_resolved(target_id, entity)
        validation = await self.adapter.validate_target(entity)
        self.targets.set_validation(target_id, validation)
        return entity, validation

    async def capture_snapshot(
        self,
        *,
        target_id: int,
        entity: ResolvedEntity,
        batch_size: int = 500,
    ) -> int:
        snapshot_id = self.snapshots.create(target_id, SnapshotState.CAPTURING)
        batch: list[TelegramMember] = []
        try:
            async for member in self.adapter.iter_accessible_members(entity):
                batch.append(member)
                if len(batch) >= batch_size:
                    self._persist_snapshot_batch(snapshot_id, batch)
                    batch = []
            if batch:
                self._persist_snapshot_batch(snapshot_id, batch)
            self.snapshots.finalize(snapshot_id)
        except Exception as exc:
            self.snapshots.mark_unavailable(snapshot_id, f"{type(exc).__name__}: {exc}")
        return snapshot_id

    def _persist_snapshot_batch(self, snapshot_id: int, batch: list[TelegramMember]) -> None:
        self.members.upsert_many(batch)
        mapping = self.members.ids_for_user_ids([member.user_id for member in batch])
        self.snapshots.add_members(
            snapshot_id, [mapping[member.user_id] for member in batch]
        )
