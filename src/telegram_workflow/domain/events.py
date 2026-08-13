from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from telegram_workflow.domain.models import CandidatePreview


@dataclass(frozen=True, slots=True)
class Event:
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class RuntimeReadyEvent(Event):
    message: str = "Core runtime ready"


@dataclass(frozen=True, slots=True)
class PongEvent(Event):
    command_id: str = ""
    payload: str = "pong"


@dataclass(frozen=True, slots=True)
class DashboardUpdatedEvent(Event):
    accounts_ready: int = 0
    jobs_running: int = 0
    jobs_paused: int = 0
    members_total: int = 0


@dataclass(frozen=True, slots=True)
class AccountsUpdatedEvent(Event):
    accounts: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class AuthCodeRequestedEvent(Event):
    account_id: int = 0
    phone: str = ""


@dataclass(frozen=True, slots=True)
class AuthPasswordRequiredEvent(Event):
    account_id: int = 0
    phone: str = ""


@dataclass(frozen=True, slots=True)
class AuthSucceededEvent(Event):
    account_id: int = 0
    phone: str = ""


@dataclass(frozen=True, slots=True)
class AccountSessionCheckedEvent(Event):
    account_id: int = 0
    healthy: bool = False


@dataclass(frozen=True, slots=True)
class SourceScanProgressEvent(Event):
    source_id: int = 0
    persisted: int = 0
    finished: bool = False


@dataclass(frozen=True, slots=True)
class SourceScanCompletedEvent(Event):
    source_id: int = 0
    total: int = 0
    members: tuple[dict[str, object], ...] = ()
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class WorkflowPreviewEvent(Event):
    target_id: int = 0
    target_snapshot_id: int | None = None
    target_title: str = ""
    permission_state: str = "UNKNOWN"
    snapshot_state: str = "UNKNOWN"
    preview: CandidatePreview = field(
        default_factory=lambda: CandidatePreview(0, 0, 0, 0, 0, 0)
    )
    members: tuple[dict[str, object], ...] = ()
    selected_member_ids: tuple[int, ...] = ()
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class ReviewJobCreatedEvent(Event):
    job_id: int = 0
    selected: int = 0


@dataclass(frozen=True, slots=True)
class MembersUpdatedEvent(Event):
    members: tuple[dict[str, object], ...] = ()
    total: int = 0
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class MemberConsentUpdatedEvent(Event):
    updated: int = 0
    consent_state: str = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class GroupsUpdatedEvent(Event):
    groups: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class JobsUpdatedEvent(Event):
    jobs: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class LogsUpdatedEvent(Event):
    entries: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class ExportCompletedEvent(Event):
    path: str = ""
    rows: int = 0
    file_format: str = "csv"


@dataclass(frozen=True, slots=True)
class RuntimeStoppedEvent(Event):
    message: str = "Core runtime stopped"


@dataclass(frozen=True, slots=True)
class SystemErrorEvent(Event):
    message: str = ""
