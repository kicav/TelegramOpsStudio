from __future__ import annotations

from telegram_workflow.domain.models import CandidatePreview, FilterConfig
from telegram_workflow.filters.engine import FilterEngine
from telegram_workflow.storage.repositories.jobs import JobMemberRepository
from telegram_workflow.storage.repositories.sources import SourceRepository
from telegram_workflow.storage.repositories.targets import TargetSnapshotRepository


class CandidateBuilder:
    def __init__(self, connection) -> None:
        self.sources = SourceRepository(connection)
        self.snapshots = TargetSnapshotRepository(connection)
        self.job_members = JobMemberRepository(connection)
        self.filter_engine = FilterEngine()

    def build(
        self,
        *,
        source_id: int,
        target_id: int,
        target_snapshot_id: int | None,
        config: FilterConfig,
        range_start: int | None = None,
        range_end: int | None = None,
        max_items: int | None = None,
    ) -> tuple[list[int], CandidatePreview]:
        source_rows = self.sources.member_rows(source_id)
        eligible = [row for row in source_rows if self.filter_engine.eligible(row, config)]
        target_member_ids = self.snapshots.member_ids(target_snapshot_id)
        previous_success = self.job_members.previous_success_member_ids(source_id, target_id)

        target_overlap = sum(1 for row in eligible if int(row["id"]) in target_member_ids)
        after_target = [row for row in eligible if int(row["id"]) not in target_member_ids]
        previous_success_count = sum(
            1 for row in after_target if int(row["id"]) in previous_success
        )
        candidates = [
            int(row["id"])
            for row in after_target
            if int(row["id"]) not in previous_success
        ]

        start = max(0, range_start or 0)
        stop = range_end if range_end is not None else len(candidates)
        selected = candidates[start:stop]
        if max_items is not None:
            selected = selected[: max(0, max_items)]

        preview = CandidatePreview(
            source_total=len(source_rows),
            eligible_after_filter=len(eligible),
            target_overlap=target_overlap,
            previous_success=previous_success_count,
            candidates=len(candidates),
            selected=len(selected),
        )
        return selected, preview
