import asyncio
from pathlib import Path

from telegram_workflow.domain.enums import AttemptResult, ErrorScope, JobMemberState, JobState
from telegram_workflow.domain.models import ActionOutcome, FilterConfig, TelegramMember
from telegram_workflow.domain.policies import RetryPolicy
from telegram_workflow.jobs.builder import JobBuilder
from telegram_workflow.jobs.runner import JobRunner
from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.members import MemberRepository
from telegram_workflow.storage.repositories.sources import SourceRepository
from telegram_workflow.storage.repositories.targets import TargetRepository
from telegram_workflow.telegram.adapter import ResolvedEntity
from tests.fakes.fake_telegram_adapter import FakeTelegramAdapter


def test_job_runner_persists_success_skip_retry_and_attempts(tmp_path: Path) -> None:
    async def scenario() -> None:
        with Database(tmp_path / "app.db") as database:
            database.migrate()
            connection = database.open()
            members = MemberRepository(connection)
            sources = SourceRepository(connection)
            targets = TargetRepository(connection)

            source_id = sources.create("source")
            source_entity = ResolvedEntity(101, "Source", None, "group")
            sources.set_resolved(source_id, source_entity)
            target_id = targets.create("target")
            target_entity = ResolvedEntity(202, "Target", None, "group")
            targets.set_resolved(target_id, target_entity)

            source_members = [TelegramMember(user_id=i, username=f"u{i}") for i in range(1, 4)]
            members.upsert_many(source_members)
            ids = members.ids_for_user_ids([1, 2, 3])
            sources.link_members(source_id, [ids[1], ids[2], ids[3]])

            job_id, _ = JobBuilder(connection).create_job(
                name="test",
                source_id=source_id,
                target_id=target_id,
                target_snapshot_id=None,
                filter_config=FilterConfig(),
            )
            fake = FakeTelegramAdapter(
                outcomes={
                    2: ActionOutcome(AttemptResult.SKIPPED, "ALREADY_MEMBER"),
                    3: ActionOutcome(
                        AttemptResult.RETRY,
                        "NETWORK_TIMEOUT",
                        scope=ErrorScope.NETWORK,
                        retry_after_seconds=-1,
                    ),
                }
            )
            runner = JobRunner(
                connection,
                fake,
                retry_policy=RetryPolicy(max_attempts=2, default_retry_seconds=0, lease_seconds=30),
            )
            await runner.run(job_id=job_id, target=target_entity)

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
            assert states[2] == JobMemberState.SKIPPED.value
            assert states[3] == JobMemberState.FINAL_FAIL.value
            job = connection.execute(
                "SELECT state, success, skipped, failed FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            assert job["state"] == JobState.COMPLETED.value
            assert (job["success"], job["skipped"], job["failed"]) == (1, 1, 1)
            attempts = connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            assert attempts == 4

    asyncio.run(scenario())
