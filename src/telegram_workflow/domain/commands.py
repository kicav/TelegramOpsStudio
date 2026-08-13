from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from telegram_workflow.domain.models import FilterConfig


@dataclass(frozen=True, slots=True)
class Command:
    command_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class PingCommand(Command):
    payload: str = "ping"


@dataclass(frozen=True, slots=True)
class RefreshDashboardCommand(Command):
    pass


@dataclass(frozen=True, slots=True)
class RefreshAccountsCommand(Command):
    pass


@dataclass(frozen=True, slots=True)
class RequestLoginCodeCommand(Command):
    profile_name: str = "Default"
    api_id: int = 0
    api_hash: str = ""
    phone: str = ""


@dataclass(frozen=True, slots=True)
class SubmitLoginCodeCommand(Command):
    phone: str = ""
    code: str = ""


@dataclass(frozen=True, slots=True)
class SubmitLoginPasswordCommand(Command):
    phone: str = ""
    password: str = ""


@dataclass(frozen=True, slots=True)
class ScanSourceCommand(Command):
    account_id: int = 0
    identifier: str = ""


@dataclass(frozen=True, slots=True)
class PreviewWorkflowCommand(Command):
    account_id: int = 0
    source_id: int = 0
    target_identifier: str = ""
    filter_config: FilterConfig = field(default_factory=FilterConfig)
    max_items: int | None = None


@dataclass(frozen=True, slots=True)
class CreateReviewJobCommand(Command):
    name: str = "Review job"
    account_id: int = 0
    source_id: int = 0
    target_id: int = 0
    target_snapshot_id: int | None = None
    filter_config: FilterConfig = field(default_factory=FilterConfig)
    max_items: int | None = None


@dataclass(frozen=True, slots=True)
class ExportMembersCommand(Command):
    member_ids: tuple[int, ...] = ()
    path: str = ""
    file_format: str = "csv"


@dataclass(frozen=True, slots=True)
class RefreshJobsCommand(Command):
    pass


@dataclass(frozen=True, slots=True)
class RefreshLogsCommand(Command):
    limit: int = 200


@dataclass(frozen=True, slots=True)
class ShutdownCommand(Command):
    reason: str = "application_exit"
