from __future__ import annotations

from dataclasses import asdict

from telegram_workflow.domain.models import CandidatePreview, FilterConfig
from telegram_workflow.jobs.candidate_builder import CandidateBuilder
from telegram_workflow.storage.repositories.jobs import JobMemberRepository, JobRepository


class JobBuilder:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.jobs = JobRepository(connection)
        self.job_members = JobMemberRepository(connection)
        self.candidates = CandidateBuilder(connection)

    def create_job(
        self,
        *,
        name: str,
        source_id: int,
        target_id: int,
        target_snapshot_id: int | None,
        filter_config: FilterConfig,
        selected_accounts: list[int] | None = None,
        range_start: int | None = None,
        range_end: int | None = None,
        max_items: int | None = None,
    ) -> tuple[int, CandidatePreview]:
        member_ids, preview = self.candidates.build(
            source_id=source_id,
            target_id=target_id,
            target_snapshot_id=target_snapshot_id,
            config=filter_config,
            range_start=range_start,
            range_end=range_end,
            max_items=max_items,
        )
        job_id = self.jobs.create(
            name=name,
            source_id=source_id,
            target_id=target_id,
            target_snapshot_id=target_snapshot_id,
            filter_snapshot=asdict(filter_config),
            selected_accounts=selected_accounts,
            range_start=range_start,
            range_end=range_end,
            max_items=max_items,
        )
        self.job_members.enqueue(job_id, member_ids)
        self.jobs.refresh_counts(job_id)
        return job_id, preview
