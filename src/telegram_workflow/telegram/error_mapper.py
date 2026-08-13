from __future__ import annotations

from datetime import UTC, datetime, timedelta

from telegram_workflow.domain.enums import AccountState, ErrorScope, JobMemberState, JobState
from telegram_workflow.domain.policies import ErrorDecision


class TelegramErrorMapper:
    """Normalize library errors without exposing raw tracebacks to business logic."""

    def map(self, exc: Exception) -> ErrorDecision:
        name = type(exc).__name__
        if name in {"FloodWaitError", "FloodWait"}:
            seconds = int(getattr(exc, "seconds", 60) or 60)
            return ErrorDecision(
                scope=ErrorScope.ACCOUNT,
                code="FLOOD_WAIT",
                retryable=True,
                retry_at=datetime.now(UTC) + timedelta(seconds=seconds),
                account_transition=AccountState.COOLDOWN,
                job_transition=JobState.PAUSED,
            )
        if name in {"SessionRevokedError", "AuthKeyUnregisteredError", "UnauthorizedError"}:
            return ErrorDecision(
                scope=ErrorScope.ACCOUNT,
                code="INVALID_SESSION",
                retryable=False,
                account_transition=AccountState.INVALID_SESSION,
            )
        if name in {"ChatAdminRequiredError", "UserNotParticipantError"}:
            return ErrorDecision(
                scope=ErrorScope.TARGET,
                code="NO_PERMISSION",
                retryable=False,
                job_transition=JobState.PAUSED,
            )
        if name in {"UserPrivacyRestrictedError", "UserChannelsTooMuchError"}:
            return ErrorDecision(
                scope=ErrorScope.MEMBER,
                code="PRIVACY_RESTRICTED",
                retryable=False,
                member_transition=JobMemberState.FINAL_FAIL,
            )
        if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
            return ErrorDecision(
                scope=ErrorScope.NETWORK,
                code="NETWORK_TRANSIENT",
                retryable=True,
                member_transition=JobMemberState.RETRY_WAIT,
            )
        return ErrorDecision(
            scope=ErrorScope.SYSTEM,
            code="UNEXPECTED_ERROR",
            retryable=False,
            member_transition=JobMemberState.FINAL_FAIL,
        )
