from pathlib import Path

from telegram_workflow.domain.enums import JobMemberState
from telegram_workflow.domain.models import FilterConfig, TelegramMember
from telegram_workflow.exports.exporter import ResultExporter
from telegram_workflow.jobs.builder import JobBuilder
from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.jobs import JobMemberRepository
from telegram_workflow.storage.repositories.members import MemberRepository
from telegram_workflow.storage.repositories.sources import SourceRepository
from telegram_workflow.storage.repositories.targets import TargetRepository
from telegram_workflow.telegram.adapter import ResolvedEntity


def test_csv_export_does_not_change_job_state(tmp_path: Path) -> None:
    with Database(tmp_path / "app.db") as database:
        database.migrate()
        connection = database.open()
        members = MemberRepository(connection)
        sources = SourceRepository(connection)
        targets = TargetRepository(connection)
        source_id = sources.create("s")
        sources.set_resolved(source_id, ResolvedEntity(301, "S", None, "group"))
        target_id = targets.create("t")
        targets.set_resolved(target_id, ResolvedEntity(302, "T", None, "group"))
        members.upsert_many([TelegramMember(user_id=9, username="nine")])
        ids = members.ids_for_user_ids([9])
        sources.link_members(source_id, [ids[9]])
        job_id, _ = JobBuilder(connection).create_job(
            name="export",
            source_id=source_id,
            target_id=target_id,
            target_snapshot_id=None,
            filter_config=FilterConfig(),
        )
        job_members = JobMemberRepository(connection)
        item = job_members.claim_next(job_id, "export", 30)
        assert item is not None
        job_members.complete(item.job_member_id, JobMemberState.SUCCESS)
        before = connection.execute(
            "SELECT state FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()["state"]
        path = tmp_path / "results.csv"
        assert ResultExporter(connection).export_job_csv(job_id, path) == 1
        assert path.exists()
        after = connection.execute(
            "SELECT state FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()["state"]
        assert after == before
