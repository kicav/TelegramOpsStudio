from pathlib import Path

from telegram_workflow.domain.enums import ActivityQuality, JobMemberState
from telegram_workflow.domain.models import FilterConfig, TelegramMember
from telegram_workflow.jobs.candidate_builder import CandidateBuilder
from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.jobs import JobMemberRepository, JobRepository
from telegram_workflow.storage.repositories.members import MemberRepository
from telegram_workflow.storage.repositories.sources import SourceRepository
from telegram_workflow.storage.repositories.targets import (
    TargetRepository,
    TargetSnapshotRepository,
)
from telegram_workflow.telegram.adapter import ResolvedEntity


def test_candidate_builder_applies_filter_snapshot_and_dedup_sets(tmp_path: Path) -> None:
    with Database(tmp_path / "app.db") as database:
        database.migrate()
        connection = database.open()
        members = MemberRepository(connection)
        sources = SourceRepository(connection)
        targets = TargetRepository(connection)
        snapshots = TargetSnapshotRepository(connection)
        jobs = JobRepository(connection)
        job_members = JobMemberRepository(connection)

        source_id = sources.create("source")
        sources.set_resolved(source_id, ResolvedEntity(100, "Source", None, "group"))
        target_id = targets.create("target")
        targets.set_resolved(target_id, ResolvedEntity(200, "Target", None, "group"))

        source_members = [
            TelegramMember(user_id=1, username="alpha", activity_quality=ActivityQuality.KNOWN),
            TelegramMember(user_id=2, username="beta", activity_quality=ActivityQuality.UNKNOWN),
            TelegramMember(user_id=3, username="gamma"),
            TelegramMember(user_id=4, username="bot", is_bot=True),
            TelegramMember(user_id=5, username="deleted", is_deleted=True),
        ]
        members.upsert_many(source_members)
        ids = members.ids_for_user_ids([m.user_id for m in source_members])
        sources.link_members(source_id, [ids[m.user_id] for m in source_members])

        snapshot_id = snapshots.create(target_id)
        snapshots.replace_members(snapshot_id, [ids[2]])

        previous_job = jobs.create(
            name="previous",
            source_id=source_id,
            target_id=target_id,
            target_snapshot_id=snapshot_id,
            filter_snapshot={},
        )
        job_members.enqueue(previous_job, [ids[3]])
        previous_item = job_members.claim_next(previous_job, "history", 30)
        assert previous_item is not None
        job_members.complete(previous_item.job_member_id, JobMemberState.SUCCESS)

        selected, preview = CandidateBuilder(connection).build(
            source_id=source_id,
            target_id=target_id,
            target_snapshot_id=snapshot_id,
            config=FilterConfig(),
        )
        assert selected == [ids[1]]
        assert preview.source_total == 5
        assert preview.eligible_after_filter == 3
        assert preview.target_overlap == 1
        assert preview.previous_success == 1
        assert preview.candidates == 1
        assert preview.selected == 1
