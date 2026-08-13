from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from telegram_workflow.diagnostics.self_check import format_self_check_json, run_self_check
from telegram_workflow.domain.commands import PingCommand, RefreshDashboardCommand
from telegram_workflow.domain.events import (
    DashboardUpdatedEvent,
    PongEvent,
    RuntimeReadyEvent,
    RuntimeStoppedEvent,
    SystemErrorEvent,
)
from telegram_workflow.runtime.core_runtime import CoreRuntime
from telegram_workflow.version import __version__


class InfoPage(QWidget):
    def __init__(self, title: str, description: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(heading)
        body = QLabel(description)
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(body)
        layout.addStretch(1)


class DashboardPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        heading = QLabel("Dashboard")
        heading.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(heading)
        self.summary = QLabel("Waiting for CoreRuntime…")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        layout.addStretch(1)

    def update_counts(self, event: DashboardUpdatedEvent) -> None:
        self.summary.setText(
            f"Ready accounts: {event.accounts_ready}\n"
            f"Running jobs: {event.jobs_running}\n"
            f"Paused jobs: {event.jobs_paused}\n"
            f"Known members: {event.members_total}"
        )


class MainWindow(QMainWindow):
    NAV_ITEMS = ["Dashboard", "Accounts", "Workflow", "Jobs", "Logs", "Settings"]

    def __init__(self, runtime: CoreRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self.setWindowTitle(f"TelegramOpsStudio {__version__}")
        self.resize(1060, 680)

        root = QWidget(self)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)

        sidebar = QFrame()
        sidebar.setMinimumWidth(190)
        side_layout = QVBoxLayout(sidebar)
        brand = QLabel("TelegramOpsStudio")
        brand.setStyleSheet("font-size: 18px; font-weight: 700; padding: 10px;")
        side_layout.addWidget(brand)
        self.navigation = QListWidget()
        for label in self.NAV_ITEMS:
            self.navigation.addItem(QListWidgetItem(label))
        side_layout.addWidget(self.navigation, 1)
        self.runtime_status = QLabel("Core: starting…")
        side_layout.addWidget(self.runtime_status)
        outer.addWidget(sidebar)

        content = QFrame()
        content_layout = QVBoxLayout(content)
        actions = QHBoxLayout()
        self.ping_button = QPushButton("Ping Core")
        self.ping_button.setEnabled(False)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setEnabled(False)
        self.check_button = QPushButton("Self Check")
        actions.addWidget(self.ping_button)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.check_button)
        actions.addStretch(1)
        content_layout.addLayout(actions)

        self.pages = QStackedWidget()
        self.dashboard_page = DashboardPage()
        self.pages.addWidget(self.dashboard_page)
        self.pages.addWidget(
            InfoPage(
                "Accounts",
                "Account/session management is isolated behind the Telegram adapter "
                "and secret store.",
            )
        )
        self.pages.addWidget(
            InfoPage(
                "Workflow",
                "Source → Filter → Target → Review → Run. Source scans only use participant "
                "lists accessible to the authenticated account.",
            )
        )
        self.pages.addWidget(
            InfoPage(
                "Jobs",
                "Persistent job state, attempts, retries, leases and recovery are stored "
                "in SQLite.",
            )
        )
        self.pages.addWidget(
            InfoPage(
                "Logs",
                "Application, operation and audit information is kept separate from "
                "secret material.",
            )
        )
        self.pages.addWidget(
            InfoPage(
                "Settings",
                "Runtime data is stored in the local application-data directory, "
                "not Program Files.",
            )
        )
        content_layout.addWidget(self.pages, 1)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(170)
        content_layout.addWidget(self.output)
        outer.addWidget(content, 1)
        self.setCentralWidget(root)

        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        self.ping_button.clicked.connect(self._ping)
        self.refresh_button.clicked.connect(self._refresh)
        self.check_button.clicked.connect(self._self_check)
        self.runtime.event_emitted.connect(self._on_event)

    def _ping(self) -> None:
        self.runtime.submit(PingCommand(payload="ui-ping"))

    def _refresh(self) -> None:
        self.runtime.submit(RefreshDashboardCommand())

    def _self_check(self) -> None:
        ok, results = run_self_check()
        self.output.setPlainText(format_self_check_json(results))
        self.statusBar().showMessage("Self check PASS" if ok else "Self check FAILED")

    def _on_event(self, event: object) -> None:
        if isinstance(event, RuntimeReadyEvent):
            self.runtime_status.setText("Core: READY")
            self.ping_button.setEnabled(True)
            self.refresh_button.setEnabled(True)
            self._refresh()
        elif isinstance(event, RuntimeStoppedEvent):
            self.runtime_status.setText("Core: STOPPED")
            self.ping_button.setEnabled(False)
            self.refresh_button.setEnabled(False)
        elif isinstance(event, PongEvent):
            self.output.append(f"PONG: {event.payload} ({event.command_id})")
        elif isinstance(event, DashboardUpdatedEvent):
            self.dashboard_page.update_counts(event)
        elif isinstance(event, SystemErrorEvent):
            self.output.append(f"ERROR: {event.message}")
