from __future__ import annotations

from telegram_workflow.domain.enums import AttemptResult, ErrorScope, JobMemberState
from telegram_workflow.domain.models import ActionOutcome, TelegramMember
from telegram_workflow.storage.repositories.attempts import AttemptRepository
from telegram_workflow.storage.repositories.jobs import JobMemberRepository
from telegram_workflow.telegram.adapter import AuthorizedActionAdapter, ResolvedEntity


class RecoveryManager:
    def __init__(self, connection, verifier: AuthorizedActionAdapter) -> None:
        self.connection = connection
        self.items = JobMemberRepository(connection)
        self.attempts = AttemptRepository(connection)
        self.verifier = verifier

    async def recover_expired(self, *, target: ResolvedEntity) -> int:
        recovered = 0
        for row in self.items.expired_processing():
            member = TelegramMember(
                user_id=int(row["telegram_user_id"]),
                access_hash=row["access_hash"],
                username=row["username"],
            )
            verified = await self.verifier.verify_authorized_action(target=target, member=member)
            if verified is True:
                outcome = ActionOutcome(
                    result=AttemptResult.SUCCESS,
                    code="RECOVERED_VERIFIED",
                    scope=ErrorScope.SYSTEM,
                )
                self.attempts.finish_latest_open(int(row["id"]), outcome)
                self.items.complete(
                    int(row["id"]),
                    JobMemberState.SUCCESS,
                    error_code=outcome.code,
                )
            else:
                # False and unknown both become READY under the conservative recovery policy.
                outcome = ActionOutcome(
                    result=AttemptResult.RETRY,
                    code="RECOVERY_RETRY",
                    scope=ErrorScope.SYSTEM,
                )
                self.attempts.finish_latest_open(int(row["id"]), outcome)
                self.items.release_processing(int(row["id"]))
            recovered += 1
        return recovered
