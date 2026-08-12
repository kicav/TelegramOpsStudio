from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from telegram_workflow.diagnostics.self_check import format_self_check_json, run_self_check
from telegram_workflow.domain.commands import PingCommand
from telegram_workflow.domain.events import PongEvent, RuntimeReadyEvent, RuntimeStoppedEvent
from telegram_workflow.runtime.core_runtime import CoreRuntime
from telegram_workflow.version import __version__


class MainWindow(QMainWindow):
    def __init__(self, runtime: CoreRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self.setWindowTitle(f"Telegram Workflow {__version__}")
        self.resize(860, 520)

        root = QWidget(self)
        layout = QVBoxLayout(root)
        title = QLabel("Telegram Workflow Desktop")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 600; padding: 12px;")
        layout.addWidget(title)

        self.runtime_status = QLabel("Core: starting...")
        layout.addWidget(self.runtime_status)

        actions = QHBoxLayout()
        self.ping_button = QPushButton("Ping Core")
        self.ping_button.setEnabled(False)
        self.check_button = QPushButton("Run Self Check")
        actions.addWidget(self.ping_button)
        actions.addWidget(self.check_button)
        layout.addLayout(actions)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)

        self.setCentralWidget(root)

        self.ping_button.clicked.connect(self._ping)
        self.check_button.clicked.connect(self._self_check)
        self.runtime.event_emitted.connect(self._on_event)

    def _ping(self) -> None:
        self.runtime.submit(PingCommand(payload="ui-ping"))

    def _self_check(self) -> None:
        ok, results = run_self_check()
        self.output.setPlainText(format_self_check_json(results))
        self.statusBar().showMessage("Self check PASS" if ok else "Self check FAILED")

    def _on_event(self, event: object) -> None:
        if isinstance(event, RuntimeReadyEvent):
            self.runtime_status.setText("Core: READY")
            self.ping_button.setEnabled(True)
        elif isinstance(event, RuntimeStoppedEvent):
            self.runtime_status.setText("Core: STOPPED")
            self.ping_button.setEnabled(False)
        elif isinstance(event, PongEvent):
            self.output.append(f"PONG: {event.payload} ({event.command_id})")
