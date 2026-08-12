from __future__ import annotations

import asyncio
import threading
import traceback

from PySide6.QtCore import QThread, Signal

from telegram_workflow.domain.commands import Command, PingCommand, ShutdownCommand
from telegram_workflow.domain.events import (
    PongEvent,
    RuntimeReadyEvent,
    RuntimeStoppedEvent,
    SystemErrorEvent,
)


class CoreRuntime(QThread):
    """Owns the background asyncio loop; UI only exchanges commands/events."""

    event_emitted = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[Command] | None = None
        self._stop_requested = threading.Event()

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
        self.event_emitted.emit(RuntimeReadyEvent())
        try:
            if self._stop_requested.is_set():
                return
            while True:
                command = await self._queue.get()
                if isinstance(command, ShutdownCommand):
                    break
                await self._handle(command)
        except Exception as exc:  # runtime boundary; normalize instead of leaking exceptions to UI
            self.event_emitted.emit(
                SystemErrorEvent(message=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            )
        finally:
            self.event_emitted.emit(RuntimeStoppedEvent())
            self._queue = None
            self._loop = None

    async def _handle(self, command: Command) -> None:
        if isinstance(command, PingCommand):
            await asyncio.sleep(0)
            self.event_emitted.emit(
                PongEvent(command_id=command.command_id, payload=command.payload)
            )
