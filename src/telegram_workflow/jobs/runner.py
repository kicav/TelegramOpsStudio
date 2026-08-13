from __future__ import annotations

import json

from telegram_workflow.accounts.scheduler import AccountScheduler
from telegram_workflow.domain.enums import AttemptResult, ErrorScope, JobMemberState, JobState
from telegram_workflow.domain.models import TelegramMember
from telegram_workflow.domain.policies import RetryPolicy
from telegram_workflow.storage.repositories.attempts import AttemptRepository
from telegram_workflow.storage.repositories.jobs import JobMemberRepository, JobRepository
from telegram_workflow.telegram.adapter import AuthorizedActionAdapter, ResolvedEntity


class JobRunner:
    """Persistent job executor for fake/admin-authorized adapters.

    Production Telethon access in this repository is read-only. This runner is fully
    testable in CI because side effects live behind AuthorizedActionAdapter.
    """

    def __init__(
        self,
        connection,
        action_adapter: AuthorizedActionAdapter,
        *,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.connection = connection
        self.jobs = JobRepository(connection)
        self.items = JobMemberRepository(connection)
        self.attempts = AttemptRepository(connection)
        self.action_adapter = action_adapter
        self.retry_policy = retry_policy or RetryPolicy()

    def _selected_accounts(self, job_id: int) -> list[int]:
        row = self.connection.execute(
            "SELECT selected_accounts_json FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Job {job_id} not found")
        return [int(value) for value in json.loads(row["selected_accounts_json"])]

    async def run(
        self,
        *,
        job_id: int,
        target: ResolvedEntity,
        worker_id: str = "worker-1",
        max_claims: int | None = None,
    ) -> None:
        selected_accounts = self._selected_accounts(job_id)
        account_scheduler = AccountScheduler(
            self.connection, selected_accounts if selected_accounts else None
        )
        self.jobs.set_state(job_id, JobState.RUNNING)
        claims = 0

        while max_claims is None or claims < max_claims:
            self.items.release_due_retries()
            claimed = self.items.claim_next(job_id, worker_id, self.retry_policy.lease_seconds)
            if claimed is None:
                break
            claims += 1
            account_id = account_scheduler.next_ready()
            member = TelegramMember(
                user_id=claimed.telegram_user_id,
                access_hash=claimed.access_hash,
                username=claimed.username,
            )
            attempt_no = claimed.attempt_count + 1
            attempt_id = self.attempts.start(claimed.job_member_id, account_id, attempt_no)
            outcome = await self.action_adapter.perform_authorized_action(
                target=target,
                member=member,
                account_id=account_id,
            )
            self.attempts.finish(attempt_id, outcome)

            if (
                outcome.scope in {ErrorScope.TARGET, ErrorScope.ACCOUNT}
                and outcome.result != AttemptResult.SUCCESS
            ):
                self.items.release_processing(
                    claimed.job_member_id,
                    increment_attempt=True,
                    error_code=outcome.code,
                    error_message=outcome.message,
                )
                self.jobs.set_state(job_id, JobState.PAUSED)
                self.jobs.refresh_counts(job_id)
                return

            if outcome.result == AttemptResult.SUCCESS:
                self.items.complete(
                    claimed.job_member_id,
                    JobMemberState.SUCCESS,
                    account_id=account_id,
                    error_code=outcome.code,
                    error_message=outcome.message,
                )
            elif outcome.result == AttemptResult.SKIPPED:
                self.items.complete(
                    claimed.job_member_id,
                    JobMemberState.SKIPPED,
                    account_id=account_id,
                    error_code=outcome.code,
                    error_message=outcome.message,
                )
            elif outcome.result == AttemptResult.RETRY and self.retry_policy.can_retry(attempt_no):
                self.items.schedule_retry(
                    claimed.job_member_id,
                    outcome.retry_after_seconds or self.retry_policy.default_retry_seconds,
                    account_id=account_id,
                    error_code=outcome.code,
                    error_message=outcome.message,
                )
            else:
                self.items.complete(
                    claimed.job_member_id,
                    JobMemberState.FINAL_FAIL,
                    account_id=account_id,
                    error_code=outcome.code,
                    error_message=outcome.message,
                )

        self.jobs.refresh_counts(job_id)
        if self.items.is_terminal(job_id):
            self.jobs.set_state(job_id, JobState.COMPLETED)
        else:
            self.jobs.set_state(job_id, JobState.PAUSED)
