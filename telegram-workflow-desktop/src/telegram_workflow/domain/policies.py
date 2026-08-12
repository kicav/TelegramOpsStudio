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
