from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Command:
    command_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class PingCommand(Command):
    payload: str = "ping"


@dataclass(frozen=True, slots=True)
class ShutdownCommand(Command):
    reason: str = "application_exit"
