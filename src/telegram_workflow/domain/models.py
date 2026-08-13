from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from .enums import ActivityQuality, AttemptResult, ErrorScope, JobMemberState


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_iso(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class TelegramMember:
    user_id: int
    access_hash: int | None = None
    username: str | None = None
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    is_bot: bool = False
    is_deleted: bool = False
    last_seen: str | None = None
    activity_quality: ActivityQuality = ActivityQuality.UNKNOWN


@dataclass(frozen=True, slots=True)
class FilterConfig:
    exclude_bots: bool = True
    exclude_deleted: bool = True
    require_username: bool = False
    username_contains: str | None = None
    allow_unknown_activity: bool = True


@dataclass(frozen=True, slots=True)
class CandidatePreview:
    source_total: int
    eligible_after_filter: int
    target_overlap: int
    previous_success: int
    candidates: int
    selected: int


@dataclass(frozen=True, slots=True)
class ClaimedJobMember:
    job_member_id: int
    job_id: int
    member_id: int
    telegram_user_id: int
    access_hash: int | None
    username: str | None
    attempt_count: int


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    result: AttemptResult
    code: str
    message: str = ""
    scope: ErrorScope = ErrorScope.MEMBER
    retry_after_seconds: int | None = None
    final_state: JobMemberState | None = None


@dataclass(frozen=True, slots=True)
class ScanProgress:
    persisted: int
    batch_size: int
    finished: bool = False


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: str
    data: str
    sessions: str
    logs: str
    exports: str
    cache: str
    backups: str


@dataclass(frozen=True, slots=True)
class AuditEntry:
    event_type: str
    entity_type: str | None = None
    entity_id: str | None = None
    details: dict[str, object] = field(default_factory=dict)
