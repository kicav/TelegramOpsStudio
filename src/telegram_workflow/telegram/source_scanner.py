from __future__ import annotations

from collections.abc import Callable

from telegram_workflow.domain.enums import SourceState
from telegram_workflow.domain.models import ScanProgress, TelegramMember
from telegram_workflow.storage.repositories.members import MemberRepository
from telegram_workflow.storage.repositories.sources import SourceRepository
from telegram_workflow.telegram.adapter import TelegramAdapter


class SourceScanner:
    def __init__(self, connection, adapter: TelegramAdapter) -> None:
        self.members = MemberRepository(connection)
        self.sources = SourceRepository(connection)
        self.adapter = adapter

    async def scan(
        self,
        *,
        source_id: int,
        identifier: str,
        batch_size: int = 500,
        on_progress: Callable[[ScanProgress], None] | None = None,
    ) -> int:
        persisted = 0
        batch: list[TelegramMember] = []
        entity = await self.adapter.resolve_entity(identifier)
        self.sources.set_resolved(source_id, entity)
        self.sources.set_scan_state(source_id, SourceState.SCANNING)
        try:
            async for member in self.adapter.iter_accessible_members(entity):
                batch.append(member)
                if len(batch) >= batch_size:
                    persisted += self._persist_batch(source_id, batch)
                    if on_progress:
                        on_progress(ScanProgress(persisted=persisted, batch_size=len(batch)))
                    batch = []
            if batch:
                persisted += self._persist_batch(source_id, batch)
                if on_progress:
                    on_progress(ScanProgress(persisted=persisted, batch_size=len(batch)))
            self.sources.set_scan_state(
                source_id, SourceState.COMPLETE, scanned_count=self.sources.count_members(source_id)
            )
            if on_progress:
                on_progress(ScanProgress(persisted=persisted, batch_size=0, finished=True))
            return self.sources.count_members(source_id)
        except Exception as exc:
            state = SourceState.PARTIAL if persisted else SourceState.FAILED
            self.sources.set_scan_state(
                source_id,
                state,
                scanned_count=self.sources.count_members(source_id),
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

    def _persist_batch(self, source_id: int, batch: list[TelegramMember]) -> int:
        self.members.upsert_many(batch)
        id_map = self.members.ids_for_user_ids([member.user_id for member in batch])
        member_ids = [id_map[member.user_id] for member in batch]
        self.sources.link_members(source_id, member_ids)
        return len(batch)
