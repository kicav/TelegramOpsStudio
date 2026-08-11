from __future__ import annotations

import asyncio
import traceback
from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class TaskSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()
    progress = Signal(int, int, str)


class AsyncTask(QRunnable):
    def __init__(self, coro_factory):
        super().__init__()
        self.coro_factory = coro_factory
        self.signals = TaskSignals()

    @Slot()
    def run(self):
        try:
            result = asyncio.run(self.coro_factory(self.signals.progress.emit))
            self.signals.result.emit(result)
        except Exception:
            self.signals.error.emit(traceback.format_exc())
        finally:
            self.signals.finished.emit()
