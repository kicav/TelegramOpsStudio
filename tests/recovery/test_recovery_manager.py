import asyncio
from pathlib import Path

from telegram_workflow.domain.enums import JobMemberState
from telegram_workflow.domain.models import FilterConfig, TelegramMember
from telegram_workflow.jobs.builder import JobBuilder
from telegram_workflow.jobs.recovery import RecoveryManager
from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.attempts import AttemptRepository
from telegram_workflow.storage.repositories.jobs import JobMemberRepository
from telegram_workflow.storage.repositories.members import MemberRepository
from telegram_workflow.storage.repositories.sources import SourceRepository
from telegram_workflow.storage.repositories.targets import TargetRepository
from telegram_workflow.telegram.adapter import ResolvedEntity
from tests.fakes.fake_telegram_adapter import FakeTelegramAdapter


def test_recovery_verifies_expired_processing_before_state_change(tmp_path: Path) -> None:
    async def scenario() -> None:
        with Database(tmp_path / "app.db") as database:
            database.migrate()
            connection = database.open()
            members = MemberRepository(connection)
            sources = SourceRepository(connection)
            targets = TargetRepository(connection)
            source_id = sources.create("source")
            sources.set_resolved(source_id, ResolvedEntity(111, "S", None, "group"))
            target_id = targets.create("target")
            target = ResolvedEntity(222, "T", None, "group")
            targets.set_resolved(target_id, target)
            members.upsert_many([TelegramMember(user_id=1), TelegramMember(user_id=2)])
            ids = members.ids_for_user_ids([1, 2])
            sources.link_members(source_id, [ids[1], ids[2]])
            job_id, _ = JobBuilder(connection).create_job(
                name="recovery",
                source_id=source_id,
                target_id=target_id,
                target_snapshot_id=None,
                filter_config=FilterConfig(),
            )
            repo = JobMemberRepository(connection)
            first = repo.claim_next(job_id, "w1", -1)
            second = repo.claim_next(job_id, "w2", -1)
            assert first is not None and second is not None
            attempts = AttemptRepository(connection)
            attempts.start(first.job_member_id, None, 1)
            attempts.start(second.job_member_id, None, 1)

            fake = FakeTelegramAdapter(verification={1: True, 2: None})
            recovered = await RecoveryManager(connection, fake).recover_expired(target=target)
            assert recovered == 2
            states = {
                row["telegram_user_id"]: row["state"]
                for row in connection.execute(
                    """
                    SELECT m.telegram_user_id, jm.state FROM job_members jm
                    JOIN members m ON m.id = jm.member_id WHERE jm.job_id = ?
                    """,
                    (job_id,),
                )
            }
            assert states[1] == JobMemberState.SUCCESS.value
            assert states[2] == JobMemberState.READY.value
            open_attempts = connection.execute(
                "SELECT COUNT(*) FROM attempts WHERE finished_at IS NULL"
            ).fetchone()[0]
            assert open_attempts == 0

    asyncio.run(scenario())
