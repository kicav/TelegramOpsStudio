from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from telegram_workflow.diagnostics.paths import runtime_paths
from telegram_workflow.diagnostics.self_check import format_self_check_json, run_self_check
from telegram_workflow.domain.commands import (
    CreateReviewJobCommand,
    ExportMembersCommand,
    PreviewWorkflowCommand,
    RefreshAccountsCommand,
    RefreshDashboardCommand,
    RefreshJobsCommand,
    RefreshLogsCommand,
    RequestLoginCodeCommand,
    ScanSourceCommand,
    SubmitLoginCodeCommand,
    SubmitLoginPasswordCommand,
)
from telegram_workflow.domain.events import (
    AccountsUpdatedEvent,
    AuthCodeRequestedEvent,
    AuthPasswordRequiredEvent,
    AuthSucceededEvent,
    DashboardUpdatedEvent,
    ExportCompletedEvent,
    JobsUpdatedEvent,
    LogsUpdatedEvent,
    ReviewJobCreatedEvent,
    RuntimeReadyEvent,
    RuntimeStoppedEvent,
    SourceScanCompletedEvent,
    SourceScanProgressEvent,
    SystemErrorEvent,
    WorkflowPreviewEvent,
)
from telegram_workflow.domain.models import FilterConfig
from telegram_workflow.runtime.core_runtime import CoreRuntime
from telegram_workflow.version import __version__


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-size: 22px; font-weight: 700;")
    return label


def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-size: 15px; font-weight: 600; margin-top: 8px;")
    return label


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    return table


def _set_table_rows(table: QTableWidget, rows: list[list[object]]) -> None:
    table.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        for column, value in enumerate(row):
            table.setItem(row_index, column, QTableWidgetItem(str(value)))


class DashboardPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(_heading("Dashboard"))
        self.summary = QLabel("Waiting for CoreRuntime…")
        self.summary.setStyleSheet("font-size: 14px; line-height: 1.4;")
        layout.addWidget(self.summary)
        info = QLabel(
            "v0.3 is read/analysis-first: account sessions, accessible member scans, "
            "filters, target snapshots, review jobs and exports. Live bulk membership actions "
            "are not enabled."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #555; margin-top: 16px;")
        layout.addWidget(info)
        layout.addStretch(1)

    def update_counts(self, event: DashboardUpdatedEvent) -> None:
        self.summary.setText(
            f"Ready accounts: {event.accounts_ready}\n"
            f"Running jobs: {event.jobs_running}\n"
            f"Paused jobs: {event.jobs_paused}\n"
            f"Known members: {event.members_total}"
        )


class AccountsPage(QWidget):
    def __init__(self, runtime: CoreRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self.pending_phone = ""
        layout = QVBoxLayout(self)
        layout.addWidget(_heading("Accounts"))
        hint = QLabel(
            "API Hash is stored in the operating-system credential store. OTP and 2FA values "
            "are used only for the current login flow and are not saved to SQLite."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555;")
        layout.addWidget(hint)

        form = QFormLayout()
        self.profile_name = QLineEdit("Default")
        self.api_id = QLineEdit()
        self.api_id.setPlaceholderText("Telegram API ID")
        self.api_hash = QLineEdit()
        self.api_hash.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_hash.setPlaceholderText("Telegram API Hash")
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("+84...")
        form.addRow("Profile", self.profile_name)
        form.addRow("API ID", self.api_id)
        form.addRow("API Hash", self.api_hash)
        form.addRow("Phone", self.phone)
        layout.addLayout(form)

        auth_buttons = QHBoxLayout()
        self.request_code = QPushButton("Send login code")
        self.refresh = QPushButton("Refresh accounts")
        auth_buttons.addWidget(self.request_code)
        auth_buttons.addWidget(self.refresh)
        auth_buttons.addStretch(1)
        layout.addLayout(auth_buttons)

        self.code_box = QFrame()
        code_layout = QFormLayout(self.code_box)
        self.code = QLineEdit()
        self.code.setPlaceholderText("Telegram login code")
        self.submit_code = QPushButton("Sign in with code")
        code_layout.addRow("Code", self.code)
        code_layout.addRow("", self.submit_code)
        self.code_box.setVisible(False)
        layout.addWidget(self.code_box)

        self.password_box = QFrame()
        password_layout = QFormLayout(self.password_box)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.submit_password = QPushButton("Submit 2FA password")
        password_layout.addRow("2FA password", self.password)
        password_layout.addRow("", self.submit_password)
        self.password_box.setVisible(False)
        layout.addWidget(self.password_box)

        self.status = QLabel("No login operation in progress.")
        layout.addWidget(self.status)
        layout.addWidget(_section("Saved accounts"))
        self.table = _table(["ID", "Phone", "Username", "State", "API profile", "Session"])
        layout.addWidget(self.table, 1)

        self.request_code.clicked.connect(self._request_code)
        self.submit_code.clicked.connect(self._submit_code)
        self.submit_password.clicked.connect(self._submit_password)
        self.refresh.clicked.connect(lambda: self.runtime.submit(RefreshAccountsCommand()))

    def _request_code(self) -> None:
        try:
            api_id = int(self.api_id.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Invalid API ID", "API ID must be an integer.")
            return
        self.pending_phone = self.phone.text().strip()
        self.status.setText("Requesting Telegram login code…")
        self.request_code.setEnabled(False)
        self.runtime.submit(
            RequestLoginCodeCommand(
                profile_name=self.profile_name.text().strip() or "Default",
                api_id=api_id,
                api_hash=self.api_hash.text(),
                phone=self.pending_phone,
            )
        )

    def _submit_code(self) -> None:
        self.runtime.submit(
            SubmitLoginCodeCommand(phone=self.pending_phone, code=self.code.text().strip())
        )

    def _submit_password(self) -> None:
        self.runtime.submit(
            SubmitLoginPasswordCommand(phone=self.pending_phone, password=self.password.text())
        )

    def set_accounts(self, accounts: tuple[dict[str, object], ...]) -> None:
        rows = [
            [a["id"], a["phone"], a["username"], a["state"], a["profile"], a["session_ref"]]
            for a in accounts
        ]
        _set_table_rows(self.table, rows)

    def code_requested(self, phone: str) -> None:
        self.pending_phone = phone
        self.code_box.setVisible(True)
        self.password_box.setVisible(False)
        self.request_code.setEnabled(True)
        self.status.setText(f"Login code sent for {phone}.")
        self.code.setFocus()

    def password_required(self, phone: str) -> None:
        self.pending_phone = phone
        self.password_box.setVisible(True)
        self.status.setText("Telegram 2FA password is required.")
        self.password.setFocus()

    def auth_succeeded(self, phone: str) -> None:
        self.request_code.setEnabled(True)
        self.code_box.setVisible(False)
        self.password_box.setVisible(False)
        self.code.clear()
        self.password.clear()
        self.api_hash.clear()
        self.status.setText(f"Account {phone} is READY.")


class WorkflowPage(QWidget):
    MEMBER_HEADERS = [
        "DB ID", "User ID", "Username", "First name", "Last name", "Phone",
        "Bot", "Deleted", "Last seen", "Activity",
    ]

    def __init__(self, runtime: CoreRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self.source_id = 0
        self.target_id = 0
        self.snapshot_id: int | None = None
        self.preview_member_ids: tuple[int, ...] = ()
        self._accounts: dict[int, str] = {}
        self._last_filter = FilterConfig()

        layout = QVBoxLayout(self)
        layout.addWidget(_heading("Workflow"))
        self.account_combo = QComboBox()
        account_row = QHBoxLayout()
        account_row.addWidget(QLabel("Account"))
        account_row.addWidget(self.account_combo, 1)
        layout.addLayout(account_row)

        layout.addWidget(_section("1. Source scan"))
        source_row = QHBoxLayout()
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("https://t.me/group or @username")
        self.scan_button = QPushButton("Resolve & Scan accessible members")
        source_row.addWidget(self.source_input, 1)
        source_row.addWidget(self.scan_button)
        layout.addLayout(source_row)
        self.scan_status = QLabel("No source scanned.")
        layout.addWidget(self.scan_status)

        layout.addWidget(_section("2. Filter"))
        filters = QHBoxLayout()
        self.exclude_bots = QCheckBox("Exclude bots")
        self.exclude_bots.setChecked(True)
        self.exclude_deleted = QCheckBox("Exclude deleted")
        self.exclude_deleted.setChecked(True)
        self.require_username = QCheckBox("Require username")
        self.allow_unknown = QCheckBox("Allow unknown activity")
        self.allow_unknown.setChecked(True)
        self.username_contains = QLineEdit()
        self.username_contains.setPlaceholderText("Username contains…")
        for widget in (
            self.exclude_bots, self.exclude_deleted, self.require_username, self.allow_unknown
        ):
            filters.addWidget(widget)
        filters.addWidget(self.username_contains, 1)
        layout.addLayout(filters)

        layout.addWidget(_section("3. Target snapshot & candidate preview"))
        target_row = QHBoxLayout()
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("Target Telegram link or @username")
        self.max_items = QSpinBox()
        self.max_items.setRange(0, 1_000_000)
        self.max_items.setSpecialValueText("All")
        self.preview_button = QPushButton("Validate target & Preview")
        target_row.addWidget(self.target_input, 1)
        target_row.addWidget(QLabel("Max"))
        target_row.addWidget(self.max_items)
        target_row.addWidget(self.preview_button)
        layout.addLayout(target_row)
        self.preview_status = QLabel("No target preview yet.")
        self.preview_status.setWordWrap(True)
        layout.addWidget(self.preview_status)

        buttons = QHBoxLayout()
        self.export_csv = QPushButton("Export preview CSV")
        self.export_xlsx = QPushButton("Export preview XLSX")
        self.create_job = QPushButton("Create review job")
        for button in (self.export_csv, self.export_xlsx, self.create_job):
            button.setEnabled(False)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.table_label = QLabel("Source members")
        self.table_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.table_label)
        self.table = _table(self.MEMBER_HEADERS)
        layout.addWidget(self.table, 1)

        self.scan_button.clicked.connect(self._scan)
        self.preview_button.clicked.connect(self._preview)
        self.export_csv.clicked.connect(lambda: self._export("csv"))
        self.export_xlsx.clicked.connect(lambda: self._export("xlsx"))
        self.create_job.clicked.connect(self._create_job)

    def set_accounts(self, accounts: tuple[dict[str, object], ...]) -> None:
        selected = self.account_combo.currentData()
        self.account_combo.clear()
        self._accounts.clear()
        for account in accounts:
            if account["state"] != "READY":
                continue
            account_id = int(account["id"])
            label = f"{account['phone']}  ·  {account['profile']}"
            self._accounts[account_id] = label
            self.account_combo.addItem(label, account_id)
        if selected is not None:
            index = self.account_combo.findData(selected)
            if index >= 0:
                self.account_combo.setCurrentIndex(index)

    def _account_id(self) -> int:
        value = self.account_combo.currentData()
        return int(value) if value is not None else 0

    def _scan(self) -> None:
        account_id = self._account_id()
        if not account_id:
            QMessageBox.warning(self, "No READY account", "Log in a Telegram account first.")
            return
        self.scan_button.setEnabled(False)
        self.scan_status.setText("Resolving source and scanning accessible participant list…")
        self.runtime.submit(
            ScanSourceCommand(account_id=account_id, identifier=self.source_input.text().strip())
        )

    def _filter_config(self) -> FilterConfig:
        contains = self.username_contains.text().strip() or None
        return FilterConfig(
            exclude_bots=self.exclude_bots.isChecked(),
            exclude_deleted=self.exclude_deleted.isChecked(),
            require_username=self.require_username.isChecked(),
            username_contains=contains,
            allow_unknown_activity=self.allow_unknown.isChecked(),
        )

    def _preview(self) -> None:
        account_id = self._account_id()
        if not account_id or not self.source_id:
            QMessageBox.warning(
                self, "Not ready", "Choose a READY account and scan a source first."
            )
            return
        self._last_filter = self._filter_config()
        max_items = self.max_items.value() or None
        self.preview_button.setEnabled(False)
        self.preview_status.setText("Validating target and capturing accessible target snapshot…")
        self.runtime.submit(
            PreviewWorkflowCommand(
                account_id=account_id,
                source_id=self.source_id,
                target_identifier=self.target_input.text().strip(),
                filter_config=self._last_filter,
                max_items=max_items,
            )
        )

    def _export(self, fmt: str) -> None:
        if not self.preview_member_ids:
            return
        filters = "CSV (*.csv)" if fmt == "csv" else "Excel (*.xlsx)"
        default = runtime_paths()["exports"] / f"candidate-preview.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, "Export preview", str(default), filters)
        if not path:
            return
        self.runtime.submit(
            ExportMembersCommand(
                member_ids=self.preview_member_ids, path=path, file_format=fmt
            )
        )

    def _create_job(self) -> None:
        if not self.target_id or not self.source_id:
            return
        self.runtime.submit(
            CreateReviewJobCommand(
                name=(
                    f"Review: {self.source_input.text().strip()} → "
                    f"{self.target_input.text().strip()}"
                ),
                account_id=self._account_id(),
                source_id=self.source_id,
                target_id=self.target_id,
                target_snapshot_id=self.snapshot_id,
                filter_config=self._last_filter,
                max_items=self.max_items.value() or None,
            )
        )

    def scan_progress(self, event: SourceScanProgressEvent) -> None:
        self.scan_status.setText(f"Persisted members: {event.persisted:,}")

    def scan_completed(self, event: SourceScanCompletedEvent) -> None:
        self.source_id = event.source_id
        self.scan_button.setEnabled(True)
        suffix = " (table limited to first 5,000)" if event.truncated else ""
        self.scan_status.setText(f"Source scan complete: {event.total:,} members{suffix}.")
        self.table_label.setText("Source members")
        self._show_members(event.members)

    def preview_completed(self, event: WorkflowPreviewEvent) -> None:
        self.target_id = event.target_id
        self.snapshot_id = event.target_snapshot_id
        self.preview_button.setEnabled(True)
        self.preview_member_ids = event.selected_member_ids
        p = event.preview
        table_note = " | table shows first 5,000" if event.truncated else ""
        self.preview_status.setText(
            f"Target: {event.target_title} | permission: {event.permission_state} | "
            f"snapshot: {event.snapshot_state}\n"
            f"Source {p.source_total:,} → eligible {p.eligible_after_filter:,} → "
            f"target overlap {p.target_overlap:,} → previous success {p.previous_success:,} → "
            f"candidates {p.candidates:,} → selected {p.selected:,}{table_note}."
        )
        self.table_label.setText("Candidate preview")
        self._show_members(event.members)
        enabled = bool(self.preview_member_ids)
        self.export_csv.setEnabled(enabled)
        self.export_xlsx.setEnabled(enabled)
        self.create_job.setEnabled(
            enabled
            and event.permission_state == "INVITE_ALLOWED"
            and event.snapshot_state == "COMPLETE"
        )

    def _show_members(self, members: tuple[dict[str, object], ...]) -> None:
        rows = [
            [
                m["id"], m["user_id"], m["username"], m["first_name"], m["last_name"],
                m["phone"], m["is_bot"], m["is_deleted"], m["last_seen"],
                m["activity_quality"],
            ]
            for m in members
        ]
        _set_table_rows(self.table, rows)


class JobsPage(QWidget):
    def __init__(self, runtime: CoreRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(_heading("Jobs"))
        self.refresh = QPushButton("Refresh")
        top.addStretch(1)
        top.addWidget(self.refresh)
        layout.addLayout(top)
        note = QLabel(
            "v0.3 jobs are persistent review queues. Live bulk membership execution is not wired."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        layout.addWidget(note)
        self.table = _table(
            [
                "ID", "Name", "State", "Total", "Success", "Skipped",
                "Failed", "Source", "Target", "Created",
            ]
        )
        layout.addWidget(self.table, 1)
        self.refresh.clicked.connect(lambda: self.runtime.submit(RefreshJobsCommand()))

    def set_jobs(self, jobs: tuple[dict[str, object], ...]) -> None:
        _set_table_rows(
            self.table,
            [
                [j["id"], j["name"], j["state"], j["total"], j["success"], j["skipped"],
                 j["failed"], j["source"], j["target"], j["created_at"]]
                for j in jobs
            ],
        )


class LogsPage(QWidget):
    def __init__(self, runtime: CoreRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(_heading("Audit Logs"))
        self.refresh = QPushButton("Refresh")
        top.addStretch(1)
        top.addWidget(self.refresh)
        layout.addLayout(top)
        self.table = _table(["Time", "Event", "Entity", "ID", "Details"])
        layout.addWidget(self.table, 1)
        self.refresh.clicked.connect(lambda: self.runtime.submit(RefreshLogsCommand()))

    def set_logs(self, entries: tuple[dict[str, object], ...]) -> None:
        _set_table_rows(
            self.table,
            [[e["created_at"], e["event_type"], e["entity_type"], e["entity_id"], e["details"]]
             for e in entries],
        )


class SettingsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(_heading("Settings & Diagnostics"))
        paths = runtime_paths()
        path_text = "\n".join(f"{name}: {path}" for name, path in paths.items())
        self.paths = QLabel(path_text)
        self.paths.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.paths)
        self.self_check = QPushButton("Run self check")
        layout.addWidget(self.self_check)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        self.self_check.clicked.connect(self._run_check)

    def _run_check(self) -> None:
        ok, results = run_self_check()
        self.output.setPlainText(format_self_check_json(results))
        self.output.append("\nPASS" if ok else "\nFAILED")


class MainWindow(QMainWindow):
    NAV_ITEMS = ["Dashboard", "Accounts", "Workflow", "Jobs", "Logs", "Settings"]

    def __init__(self, runtime: CoreRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self.setWindowTitle(f"TelegramOpsStudio {__version__}")
        self.resize(1240, 780)

        root = QWidget(self)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(210)
        side_layout = QVBoxLayout(sidebar)
        brand = QLabel("TelegramOpsStudio")
        brand.setObjectName("brand")
        side_layout.addWidget(brand)
        version = QLabel(f"v{__version__}")
        version.setObjectName("versionLabel")
        side_layout.addWidget(version)
        self.navigation = QListWidget()
        for label in self.NAV_ITEMS:
            self.navigation.addItem(QListWidgetItem(label))
        side_layout.addWidget(self.navigation, 1)
        self.runtime_status = QLabel("Core: starting…")
        self.runtime_status.setObjectName("runtimeStatus")
        side_layout.addWidget(self.runtime_status)
        outer.addWidget(sidebar)

        self.pages = QStackedWidget()
        self.dashboard_page = DashboardPage()
        self.accounts_page = AccountsPage(runtime)
        self.workflow_page = WorkflowPage(runtime)
        self.jobs_page = JobsPage(runtime)
        self.logs_page = LogsPage(runtime)
        self.settings_page = SettingsPage()
        for page in (
            self.dashboard_page, self.accounts_page, self.workflow_page,
            self.jobs_page, self.logs_page, self.settings_page,
        ):
            self.pages.addWidget(page)
        outer.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #f5f7fb;
                color: #172033;
                font-size: 13px;
            }
            QFrame#sidebar {
                background: #172033;
                border: none;
            }
            QLabel#brand {
                background: transparent;
                color: white;
                font-size: 19px;
                font-weight: 700;
                padding: 12px 10px 2px 10px;
            }
            QLabel#versionLabel {
                background: transparent;
                color: #9fb0cf;
                padding: 0 10px 10px 10px;
            }
            QLabel#runtimeStatus {
                background: transparent;
                color: #b8c5dc;
                padding: 10px;
            }
            QFrame#sidebar QListWidget {
                background: transparent;
                color: #dce5f5;
                border: none;
                outline: none;
            }
            QFrame#sidebar QListWidget::item {
                padding: 10px 12px;
                margin: 2px 4px;
                border-radius: 6px;
            }
            QFrame#sidebar QListWidget::item:selected {
                background: #2f6fed;
                color: white;
            }
            QLineEdit, QComboBox, QSpinBox, QTextEdit {
                background: white;
                border: 1px solid #d9dfeb;
                border-radius: 6px;
                padding: 6px 8px;
                selection-background-color: #2f6fed;
            }
            QPushButton {
                background: #2f6fed;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 7px 12px;
                min-height: 18px;
            }
            QPushButton:hover { background: #255fd2; }
            QPushButton:disabled { background: #b8c2d6; color: #eef1f6; }
            QCheckBox { spacing: 6px; }
            QTableWidget {
                background: white;
                alternate-background-color: #f8faff;
                border: 1px solid #dfe5ef;
                border-radius: 6px;
                gridline-color: #edf0f5;
            }
            QHeaderView::section {
                background: #eef2f8;
                color: #33415c;
                border: none;
                border-bottom: 1px solid #d7deea;
                padding: 7px;
                font-weight: 600;
            }
            QStatusBar { background: white; border-top: 1px solid #e2e7ef; }
            """
        )

        self.navigation.currentRowChanged.connect(self._navigate)
        self.navigation.setCurrentRow(0)
        self.runtime.event_emitted.connect(self._on_event)
        self.statusBar().showMessage("Starting CoreRuntime…")

    def _navigate(self, row: int) -> None:
        self.pages.setCurrentIndex(row)
        if row == 1:
            self.runtime.submit(RefreshAccountsCommand())
        elif row == 3:
            self.runtime.submit(RefreshJobsCommand())
        elif row == 4:
            self.runtime.submit(RefreshLogsCommand())
        elif row == 0:
            self.runtime.submit(RefreshDashboardCommand())

    def _on_event(self, event: object) -> None:
        if isinstance(event, RuntimeReadyEvent):
            self.runtime_status.setText("Core: READY")
            self.statusBar().showMessage("Core ready")
        elif isinstance(event, RuntimeStoppedEvent):
            self.runtime_status.setText("Core: STOPPED")
        elif isinstance(event, DashboardUpdatedEvent):
            self.dashboard_page.update_counts(event)
        elif isinstance(event, AccountsUpdatedEvent):
            self.accounts_page.set_accounts(event.accounts)
            self.workflow_page.set_accounts(event.accounts)
        elif isinstance(event, AuthCodeRequestedEvent):
            self.accounts_page.code_requested(event.phone)
            self.statusBar().showMessage("Telegram login code requested")
        elif isinstance(event, AuthPasswordRequiredEvent):
            self.accounts_page.password_required(event.phone)
        elif isinstance(event, AuthSucceededEvent):
            self.accounts_page.auth_succeeded(event.phone)
            self.statusBar().showMessage(f"Account {event.phone} ready")
        elif isinstance(event, SourceScanProgressEvent):
            self.workflow_page.scan_progress(event)
        elif isinstance(event, SourceScanCompletedEvent):
            self.workflow_page.scan_completed(event)
            self.statusBar().showMessage(f"Scanned {event.total:,} members")
        elif isinstance(event, WorkflowPreviewEvent):
            self.workflow_page.preview_completed(event)
            self.statusBar().showMessage(f"Preview selected {event.preview.selected:,} candidates")
        elif isinstance(event, ReviewJobCreatedEvent):
            self.statusBar().showMessage(f"Review job #{event.job_id} created")
            QMessageBox.information(
                self,
                "Review job created",
                f"Job #{event.job_id} contains {event.selected} candidates.",
            )
        elif isinstance(event, JobsUpdatedEvent):
            self.jobs_page.set_jobs(event.jobs)
        elif isinstance(event, LogsUpdatedEvent):
            self.logs_page.set_logs(event.entries)
        elif isinstance(event, ExportCompletedEvent):
            self.statusBar().showMessage(f"Exported {event.rows} rows")
            QMessageBox.information(
                self, "Export complete", f"Saved {event.rows} rows to:\n{event.path}"
            )
        elif isinstance(event, SystemErrorEvent):
            self.accounts_page.request_code.setEnabled(True)
            self.workflow_page.scan_button.setEnabled(True)
            self.workflow_page.preview_button.setEnabled(True)
            self.statusBar().showMessage("Operation failed")
            QMessageBox.critical(self, "Operation failed", event.message)
