from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


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
class RuntimeStoppedEvent(Event):
    message: str = "Core runtime stopped"


@dataclass(frozen=True, slots=True)
class SystemErrorEvent(Event):
    message: str = ""
