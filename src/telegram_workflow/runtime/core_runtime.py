from __future__ import annotations

import asyncio
import threading
import traceback

from PySide6.QtCore import QThread, Signal

from telegram_workflow.diagnostics.paths import ensure_runtime_dirs
from telegram_workflow.domain.commands import (
    Command,
    PingCommand,
    RefreshDashboardCommand,
    ShutdownCommand,
)
from telegram_workflow.domain.enums import AccountState, JobState
from telegram_workflow.domain.events import (
    DashboardUpdatedEvent,
    PongEvent,
    RuntimeReadyEvent,
    RuntimeStoppedEvent,
    SystemErrorEvent,
)
from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.accounts import AccountRepository
from telegram_workflow.storage.repositories.jobs import JobRepository
from telegram_workflow.storage.repositories.members import MemberRepository


class CoreRuntime(QThread):
    """Owns the background asyncio loop and the application SQLite connection."""

    event_emitted = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[Command] | None = None
        self._stop_requested = threading.Event()
        self._database: Database | None = None

    def submit(self, command: Command) -> bool:
        loop = self._loop
        queue = self._queue
        if loop is None or queue is None or loop.is_closed():
            return False
        loop.call_soon_threadsafe(queue.put_nowait, command)
        return True

    def request_stop(self) -> None:
        self._stop_requested.set()
        self.submit(ShutdownCommand())

    def run(self) -> None:
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        try:
            paths = ensure_runtime_dirs()
            self._database = Database(paths["data"] / "app.db")
            self._database.open()
            self._database.migrate()
            self.event_emitted.emit(RuntimeReadyEvent())
            if self._stop_requested.is_set():
                return
            while True:
                command = await self._queue.get()
                if isinstance(command, ShutdownCommand):
                    break
                await self._handle(command)
        except Exception as exc:  # runtime boundary; UI receives a normalized error event
            self.event_emitted.emit(
                SystemErrorEvent(message=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            )
        finally:
            if self._database is not None:
                self._database.close()
            self._database = None
            self.event_emitted.emit(RuntimeStoppedEvent())
            self._queue = None
            self._loop = None

    async def _handle(self, command: Command) -> None:
        if isinstance(command, PingCommand):
            await asyncio.sleep(0)
            self.event_emitted.emit(
                PongEvent(command_id=command.command_id, payload=command.payload)
            )
        elif isinstance(command, RefreshDashboardCommand):
            self._emit_dashboard()

    def _emit_dashboard(self) -> None:
        if self._database is None:
            return
        connection = self._database.open()
        accounts = AccountRepository(connection)
        jobs = JobRepository(connection)
        members = MemberRepository(connection)
        self.event_emitted.emit(
            DashboardUpdatedEvent(
                accounts_ready=accounts.count_by_state(AccountState.READY),
                jobs_running=jobs.counts_by_state(JobState.RUNNING),
                jobs_paused=jobs.counts_by_state(JobState.PAUSED),
                members_total=members.count(),
            )
        )
