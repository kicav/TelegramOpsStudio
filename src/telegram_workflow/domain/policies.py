from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .enums import AccountState, ErrorScope, JobMemberState, JobState


@dataclass(frozen=True, slots=True)
class ErrorDecision:
    scope: ErrorScope
    code: str
    retryable: bool
    retry_at: datetime | None = None
    member_transition: JobMemberState | None = None
    account_transition: AccountState | None = None
    job_transition: JobState | None = None


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    default_retry_seconds: int = 60
    lease_seconds: int = 120

    def can_retry(self, attempt_count: int) -> bool:
        return attempt_count < self.max_attempts
