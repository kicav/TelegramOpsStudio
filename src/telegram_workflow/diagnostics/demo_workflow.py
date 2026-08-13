from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from telegram_workflow.domain.enums import AttemptResult
from telegram_workflow.domain.models import ActionOutcome, FilterConfig, TelegramMember
from telegram_workflow.jobs.builder import JobBuilder
from telegram_workflow.jobs.runner import JobRunner
from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.sources import SourceRepository
from telegram_workflow.storage.repositories.targets import (
    TargetRepository,
    TargetSnapshotRepository,
)
from telegram_workflow.telegram.adapter import ResolvedEntity
from telegram_workflow.telegram.fake_adapter import FakeTelegramAdapter
from telegram_workflow.telegram.source_scanner import SourceScanner


async def _run_demo() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="telegram-ops-demo-") as tmp:
        with Database(Path(tmp) / "demo.db") as database:
            database.migrate()
            connection = database.open()
            sources = SourceRepository(connection)
            targets = TargetRepository(connection)
            snapshots = TargetSnapshotRepository(connection)

            source_members = [
                TelegramMember(user_id=1, username="alpha"),
                TelegramMember(user_id=2, username="beta"),
                TelegramMember(user_id=3, username="gamma"),
                TelegramMember(user_id=4, username="robot", is_bot=True),
            ]
            adapter = FakeTelegramAdapter(
                source_members,
                outcomes={3: ActionOutcome(AttemptResult.SKIPPED, "FAKE_SKIP")},
            )
            source_id = sources.create("fake-source")
            scanned = await SourceScanner(connection, adapter).scan(
                source_id=source_id,
                identifier="fake-source",
                batch_size=2,
            )

            target_id = targets.create("fake-target")
            target_entity = ResolvedEntity(987654, "Fake target", None, "fake_group")
            targets.set_resolved(target_id, target_entity)

            member_two = connection.execute(
                "SELECT id FROM members WHERE telegram_user_id = 2"
            ).fetchone()["id"]
            snapshot_id = snapshots.create(target_id)
            snapshots.replace_members(snapshot_id, [member_two])

            job_id, preview = JobBuilder(connection).create_job(
                name="demo-job",
                source_id=source_id,
                target_id=target_id,
                target_snapshot_id=snapshot_id,
                filter_config=FilterConfig(),
            )
            await JobRunner(connection, adapter).run(job_id=job_id, target=target_entity)
            job = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return {
                "scanned_members": scanned,
                "preview": {
                    "source_total": preview.source_total,
                    "eligible_after_filter": preview.eligible_after_filter,
                    "target_overlap": preview.target_overlap,
                    "candidates": preview.candidates,
                    "selected": preview.selected,
                },
                "job": {
                    "state": job["state"],
                    "total": job["total"],
                    "success": job["success"],
                    "skipped": job["skipped"],
                    "failed": job["failed"],
                },
            }


def run_demo_workflow() -> str:
    return json.dumps(asyncio.run(_run_demo()), indent=2, ensure_ascii=False)
