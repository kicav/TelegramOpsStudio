from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import credentials
from .config import APP_DISPLAY_NAME, APP_VERSION, DOWNLOADS_DIR, SESSIONS_DIR, ensure_dirs
from .db import Database
from .exporter import export_csv, export_xlsx, import_xlsx
from .license_updater import check_update, download_verified, read_license
from .tasks import AsyncTask
from .telegram_service import (
    InviteService,
    JoinService,
    MessageArchiveService,
    MessengerService,
    ScannerService,
    ScriptService,
    TwoFactorRequired,
    complete_login_code,
    complete_login_password,
    request_login_code,
)


MEMBER_COLUMNS = [
    "id", "user_id", "username", "first_name", "last_name", "has_photo", "last_seen",
    "source_group", "consent_status", "status",
]


def table_set(table: QTableWidget, rows, columns: list[str]) -> None:
    table.clearContents()
    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        keys = row.keys() if hasattr(row, "keys") else row
        for column_index, key in enumerate(columns):
            value = row[key] if key in keys else ""
            table.setItem(row_index, column_index, QTableWidgetItem("" if value is None else str(value)))
    table.resizeColumnsToContents()


def selected_id(table: QTableWidget, column: int = 0) -> int | None:
    row = table.currentRow()
    if row < 0:
        return None
    item = table.item(row, column)
    if item is None:
        return None
    try:
        return int(item.text())
    except ValueError:
        return None


class AccountCombo(QComboBox):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.reload()

    def reload(self) -> None:
        current = self.currentData()
        self.clear()
        for account in self.db.accounts():
            username = f"@{account['username']}" if account["username"] else ""
            self.addItem(f"{account['phone']} {username}".strip(), account["id"])
        if current is not None:
            index = self.findData(current)
            if index >= 0:
                self.setCurrentIndex(index)


class DashboardTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.labels: dict[str, QLabel] = {}
        layout = QVBoxLayout(self)
        title = QLabel(f"{APP_DISPLAY_NAME} — Dashboard")
        title.setStyleSheet("font-size:22px;font-weight:700")
        layout.addWidget(title)
        grid = QGridLayout()
        layout.addLayout(grid)
        metrics = [
            ("accounts", "Accounts"),
            ("members", "Members"),
            ("opted_in", "Opted-in"),
            ("jobs", "Jobs"),
            ("success_actions", "Successful actions"),
        ]
        for index, (key, label_text) in enumerate(metrics):
            box = QGroupBox(label_text)
            box_layout = QVBoxLayout(box)
            value = QLabel("0")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setStyleSheet("font-size:26px;font-weight:700")
            box_layout.addWidget(value)
            grid.addWidget(box, index // 3, index % 3)
            self.labels[key] = value
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)
        layout.addStretch()
        self.refresh()

    def refresh(self) -> None:
        for key, value in self.db.stats().items():
            self.labels[key].setText(str(value))


class AccountsTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.pool = QThreadPool.globalInstance()
        self._pending_auth: dict | None = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("+84...")
        self.api_id = QLineEdit()
        self.api_hash = QLineEdit()
        self.api_hash.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Phone", self.phone)
        form.addRow("API ID", self.api_id)
        form.addRow("API Hash", self.api_hash)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        authorize = QPushButton("Authorize / Add session")
        authorize.clicked.connect(self.authorize)
        delete = QPushButton("Delete selected account")
        delete.clicked.connect(self.delete_selected)
        buttons.addWidget(authorize)
        buttons.addWidget(delete)
        layout.addLayout(buttons)

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.table = QTableWidget()
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        table_set(
            self.table,
            self.db.accounts(),
            [
                "id", "phone", "username", "display_name", "status", "proxy_label",
                "invite_success_total", "message_success_total", "daily_invite_count", "last_used_at",
            ],
        )

    def authorize(self) -> None:
        phone = self.phone.text().strip()
        api_hash = self.api_hash.text().strip()
        try:
            api_id = int(self.api_id.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Input", "API ID must be an integer")
            return
        if not phone or not api_hash:
            QMessageBox.warning(self, "Input", "Phone and API Hash are required")
            return

        ensure_dirs()
        safe_phone = "".join(ch for ch in phone if ch.isdigit())
        session_file = str(SESSIONS_DIR / safe_phone)
        self._pending_auth = {
            "phone": phone,
            "api_id": api_id,
            "api_hash": api_hash,
            "session_file": session_file,
        }
        self.status.setText("Requesting Telegram login code...")

        async def factory(_progress):
            return await request_login_code(phone, api_id, api_hash, session_file)

        task = AsyncTask(factory)
        task.signals.result.connect(self._code_requested)
        task.signals.error.connect(lambda error: self._auth_error("Could not request login code", error))
        self.pool.start(task)

    def _code_requested(self, phone_code_hash: str) -> None:
        if not self._pending_auth:
            return
        if phone_code_hash == "ALREADY_AUTHORIZED":
            self._finish_password("")
            return
        code, ok = QInputDialog.getText(self, "Telegram login", "Enter the login code sent by Telegram")
        if not ok or not code.strip():
            self.status.setText("Authorization cancelled")
            return

        values = dict(self._pending_auth)

        async def factory(_progress):
            try:
                return await complete_login_code(
                    self.db,
                    values["phone"],
                    values["api_id"],
                    values["api_hash"],
                    values["session_file"],
                    code,
                    phone_code_hash,
                )
            except TwoFactorRequired:
                return {"two_factor_required": True}

        self.status.setText("Verifying login code...")
        task = AsyncTask(factory)
        task.signals.result.connect(self._login_code_done)
        task.signals.error.connect(lambda error: self._auth_error("Login failed", error))
        self.pool.start(task)

    def _login_code_done(self, result: dict) -> None:
        if result.get("two_factor_required"):
            password, ok = QInputDialog.getText(
                self,
                "Telegram 2FA",
                "Enter the Telegram two-step verification password",
                QLineEdit.EchoMode.Password,
            )
            if not ok:
                self.status.setText("2FA cancelled")
                return
            self._finish_password(password)
            return
        self._auth_success(result)

    def _finish_password(self, password: str) -> None:
        if not self._pending_auth:
            return
        values = dict(self._pending_auth)

        async def factory(_progress):
            return await complete_login_password(
                self.db,
                values["phone"],
                values["api_id"],
                values["api_hash"],
                values["session_file"],
                password,
            )

        self.status.setText("Completing authorization...")
        task = AsyncTask(factory)
        task.signals.result.connect(self._auth_success)
        task.signals.error.connect(lambda error: self._auth_error("2FA login failed", error))
        self.pool.start(task)

    def _auth_success(self, result: dict) -> None:
        self.status.setText(f"Authorized: {result.get('phone', '')} @{result.get('username', '')}")
        self.api_hash.clear()
        self._pending_auth = None
        self.refresh()
        QMessageBox.information(self, "Account", "Telegram session authorized successfully")

    def _auth_error(self, title: str, detail: str) -> None:
        self.status.setText(title)
        QMessageBox.critical(self, title, detail)

    def delete_selected(self) -> None:
        account_id = selected_id(self.table)
        if account_id is None:
            return
        account = self.db.account(account_id)
        if not account:
            return
        answer = QMessageBox.question(
            self,
            "Delete account",
            "Remove the account, stored API Hash and local Telegram session file?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            credentials.delete_api_hash(account["phone"])
        except Exception:
            # Local account/session cleanup must still be possible if the OS
            # credential backend is temporarily unavailable.
            pass
        base = Path(account["session_file"])
        for suffix in ("", ".session", ".session-journal", ".session-wal", ".session-shm"):
            candidate = base if not suffix else Path(str(base) + suffix)
            candidate.unlink(missing_ok=True)
        self.db.delete_account(account_id)
        self.refresh()


class ScannerTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.scanner = ScannerService(db)
        self.pool = QThreadPool.globalInstance()
        self.dialog_rows: list[dict] = []

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.account = AccountCombo(db)
        self.group = QLineEdit()
        self.group.setPlaceholderText("@group, t.me link, or joined group identifier")
        self.scan_limit = QSpinBox()
        self.scan_limit.setRange(1, 100000)
        self.scan_limit.setValue(int(db.get_setting("scan_limit", "5000")))
        top.addWidget(self.account)
        top.addWidget(self.group, 1)
        top.addWidget(QLabel("Limit"))
        top.addWidget(self.scan_limit)
        layout.addLayout(top)

        options = QHBoxLayout()
        self.filter_bots = QCheckBox("Filter bots")
        self.filter_bots.setChecked(True)
        self.filter_deleted = QCheckBox("Filter deleted")
        self.filter_deleted.setChecked(True)
        options.addWidget(self.filter_bots)
        options.addWidget(self.filter_deleted)
        options.addStretch()
        layout.addLayout(options)

        buttons = QHBoxLayout()
        joined = QPushButton("Get joined groups")
        joined.clicked.connect(self.load_joined)
        overview = QPushButton("Public overview")
        overview.clicked.connect(self.overview)
        scan = QPushButton("Detailed scan — managed group")
        scan.clicked.connect(self.scan)
        export_csv_button = QPushButton("Export CSV")
        export_csv_button.clicked.connect(lambda: self.export(False))
        export_xlsx_button = QPushButton("Export XLSX")
        export_xlsx_button.clicked.connect(lambda: self.export(True))
        import_button = QPushButton("Import members")
        import_button.clicked.connect(self.import_members)
        for button in (joined, overview, scan, export_csv_button, export_xlsx_button, import_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.table = QTableWidget()
        self.table.itemDoubleClicked.connect(self._dialog_double_clicked)
        layout.addWidget(self.table)
        self.refresh_members()

    def _account(self) -> int:
        value = self.account.currentData()
        if value is None:
            raise ValueError("Add and select a Telegram account first")
        return int(value)

    def _run(self, factory, done) -> None:
        task = AsyncTask(factory)
        task.signals.progress.connect(lambda i, n, text: self.status.setText(f"{i}/{n}: {text}"))
        task.signals.result.connect(done)
        task.signals.error.connect(lambda error: QMessageBox.critical(self, "Task failed", error))
        self.pool.start(task)

    def load_joined(self) -> None:
        async def factory(_progress):
            return await self.scanner.list_joined_groups(self._account())
        self._run(factory, self._joined_done)

    def _joined_done(self, rows: list[dict]) -> None:
        self.dialog_rows = rows
        self.status.setText(f"Loaded {len(rows)} joined groups/channels. Double-click a row to select it.")
        table_set(self.table, rows, ["peer_id", "title", "identifier", "participants"])

    def _dialog_double_clicked(self, item: QTableWidgetItem) -> None:
        if not self.dialog_rows:
            return
        row = item.row()
        if 0 <= row < len(self.dialog_rows):
            self.group.setText(str(self.dialog_rows[row]["identifier"]))

    def overview(self) -> None:
        async def factory(_progress):
            return await self.scanner.overview(self._account(), self.group.text().strip())
        self._run(factory, lambda result: self.status.setText(str(result)))

    def scan(self) -> None:
        async def factory(progress):
            return await self.scanner.scan_managed(
                self._account(),
                self.group.text().strip(),
                self.scan_limit.value(),
                self.filter_bots.isChecked(),
                self.filter_deleted.isChecked(),
                progress,
            )
        self._run(factory, self._scan_done)

    def _scan_done(self, result: dict) -> None:
        self.status.setText(f"Saved {result['saved']} member records from {result['title']}")
        self.refresh_members()

    def refresh_members(self) -> None:
        self.dialog_rows = []
        table_set(self.table, self.db.member_rows(limit=2000), MEMBER_COLUMNS)

    def export(self, xlsx: bool) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export members",
            "members.xlsx" if xlsx else "members.csv",
            "Excel (*.xlsx)" if xlsx else "CSV (*.csv)",
        )
        if not path:
            return
        rows = self.db.member_rows()
        (export_xlsx if xlsx else export_csv)(rows, path)
        self.status.setText(f"Exported {len(rows)} records to {path}")

    def import_members(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import members", "", "Members (*.csv *.xlsx)")
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                count = self.db.import_csv(path)
            else:
                grouped: dict[tuple[str, bool], list[dict]] = {}
                for row in import_xlsx(path):
                    source = str(row.get("source_group") or "import")
                    normalized = self.db.normalize_import_row(row)
                    managed = bool(normalized.pop("source_managed", False))
                    grouped.setdefault((source, managed), []).append(normalized)
                count = sum(
                    self.db.save_members(rows, source, managed)
                    for (source, managed), rows in grouped.items()
                )
            self.refresh_members()
            QMessageBox.information(self, "Import", f"Imported {count} records")
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))


class FilterTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)

        first = QHBoxLayout()
        self.exclude_bots = QCheckBox("Exclude bots")
        self.exclude_bots.setChecked(True)
        self.exclude_deleted = QCheckBox("Exclude deleted")
        self.exclude_deleted.setChecked(True)
        self.consent = QComboBox()
        self.consent.addItems(["All", "opted_in", "opted_out", "unknown"])
        self.source = QComboBox()
        self.source.addItem("All sources", None)
        self.photo = QComboBox()
        self.photo.addItem("All photos", "all")
        self.photo.addItem("Has photo", "has_photo")
        self.photo.addItem("No photo", "no_photo")
        for widget in (
            self.exclude_bots, self.exclude_deleted, QLabel("Consent"), self.consent,
            QLabel("Source"), self.source, QLabel("Photo"), self.photo,
        ):
            first.addWidget(widget)
        layout.addLayout(first)

        second = QHBoxLayout()
        self.username = QLineEdit()
        self.username.setPlaceholderText("Username contains...")
        self.activity_enabled = QCheckBox("Active within exact days")
        self.activity_days = QSpinBox()
        self.activity_days.setRange(1, 3650)
        self.activity_days.setValue(30)
        apply_button = QPushButton("Apply filters")
        apply_button.clicked.connect(self.refresh)
        second.addWidget(self.username, 1)
        second.addWidget(self.activity_enabled)
        second.addWidget(self.activity_days)
        second.addWidget(apply_button)
        layout.addLayout(second)

        self.table = QTableWidget()
        layout.addWidget(self.table)
        marks = QHBoxLayout()
        for status in ("opted_in", "opted_out", "unknown"):
            button = QPushButton(f"Mark selected: {status}")
            button.clicked.connect(lambda _checked=False, value=status: self.mark(value))
            marks.addWidget(button)
        layout.addLayout(marks)
        self.reload_sources()
        self.refresh()

    def reload_sources(self) -> None:
        current = self.source.currentData()
        self.source.clear()
        self.source.addItem("All sources", None)
        for source in self.db.member_sources():
            self.source.addItem(source, source)
        if current is not None:
            index = self.source.findData(current)
            if index >= 0:
                self.source.setCurrentIndex(index)

    def refresh(self) -> None:
        consent = None if self.consent.currentText() == "All" else self.consent.currentText()
        days = self.activity_days.value() if self.activity_enabled.isChecked() else None
        rows = self.db.member_rows(
            bots=not self.exclude_bots.isChecked(),
            deleted=not self.exclude_deleted.isChecked(),
            consent=consent,
            source=self.source.currentData(),
            username_contains=self.username.text(),
            photo_filter=str(self.photo.currentData()),
            active_within_days=days,
            limit=10000,
        )
        table_set(self.table, rows, MEMBER_COLUMNS)

    def mark(self, status: str) -> None:
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item:
                self.db.set_consent(int(item.text()), status, "Set in Filter & Consent tab")
        self.refresh()


class InviteTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.service = InviteService(db)
        self.pool = QThreadPool.globalInstance()
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.account = AccountCombo(db)
        self.target = QLineEdit()
        self.source = QComboBox()
        self.offset = QSpinBox()
        self.offset.setRange(0, 1_000_000)
        self.limit = QSpinBox()
        self.limit.setRange(1, 500)
        self.limit.setValue(20)
        self.dry = QCheckBox("Dry run")
        self.dry.setChecked(True)
        form.addRow("Account", self.account)
        form.addRow("Managed target group", self.target)
        form.addRow("Member source", self.source)
        form.addRow("Start offset", self.offset)
        form.addRow("Max opted-in users", self.limit)
        form.addRow("Safety", self.dry)
        layout.addLayout(form)
        start = QPushButton("Run invite queue")
        start.clicked.connect(self.run)
        layout.addWidget(start)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        note = QLabel(
            "Only explicitly opted-in records are eligible. The target must be administered by the selected account. "
            "FloodWait/restriction stops the job; the app does not rotate accounts or proxies to bypass Telegram limits."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        self.reload_sources()

    def reload_sources(self) -> None:
        current = self.source.currentData()
        self.source.clear()
        self.source.addItem("All sources", None)
        for source in self.db.member_sources():
            self.source.addItem(source, source)
        if current is not None:
            index = self.source.findData(current)
            if index >= 0:
                self.source.setCurrentIndex(index)

    def run(self) -> None:
        account_id = self.account.currentData()
        if account_id is None:
            QMessageBox.warning(self, "Invite", "Add and select an account first")
            return
        try:
            delay_min = float(self.db.get_setting("invite_delay_min", "8"))
            delay_max = float(self.db.get_setting("invite_delay_max", "15"))
        except ValueError:
            QMessageBox.warning(self, "Settings", "Invite delay settings must be numbers")
            return

        async def factory(progress):
            return await self.service.run(
                int(account_id), self.target.text().strip(), self.limit.value(), delay_min, delay_max,
                self.dry.isChecked(), progress, self.source.currentData(), self.offset.value(),
            )

        task = AsyncTask(factory)
        task.signals.progress.connect(lambda i, n, text: self.status.setText(f"{i}/{n}: {text}"))
        task.signals.result.connect(
            lambda result: self.status.setText(
                f"Success={result.success} Failed={result.failed} Skipped={result.skipped} {result.stopped_reason}"
            )
        )
        task.signals.error.connect(lambda error: QMessageBox.critical(self, "Invite failed", error))
        self.pool.start(task)


class MessengerTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.service = MessengerService(db)
        self.pool = QThreadPool.globalInstance()
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        group = QWidget()
        form = QFormLayout(group)
        self.group_account = AccountCombo(db)
        self.group_target = QLineEdit()
        self.group_text = QTextEdit()
        self.group_file = QLineEdit()
        file_button = QPushButton("Choose file")
        file_button.clicked.connect(lambda: self._choose_file(self.group_file))
        send = QPushButton("Send to managed group")
        send.clicked.connect(self.send_group)
        form.addRow("Account", self.group_account)
        form.addRow("Managed group", self.group_target)
        form.addRow("Message", self.group_text)
        attachment_row = QHBoxLayout()
        attachment_row.addWidget(self.group_file)
        attachment_row.addWidget(file_button)
        form.addRow("Attachment", attachment_row)
        form.addRow(send)
        tabs.addTab(group, "Group")

        many = QWidget()
        many_form = QFormLayout(many)
        self.many_account = AccountCombo(db)
        self.many_targets = QTextEdit()
        self.many_targets.setPlaceholderText("One managed group per line")
        self.many_text = QTextEdit()
        self.many_file = QLineEdit()
        many_file_button = QPushButton("Choose file")
        many_file_button.clicked.connect(lambda: self._choose_file(self.many_file))
        self.many_delay = QDoubleSpinBox()
        self.many_delay.setRange(0, 3600)
        self.many_delay.setValue(2)
        self.many_status = QLabel()
        many_send = QPushButton("Send to managed groups")
        many_send.clicked.connect(self.send_many_groups)
        many_form.addRow("Account", self.many_account)
        many_form.addRow("Managed groups", self.many_targets)
        many_form.addRow("Message", self.many_text)
        many_attachment_row = QHBoxLayout()
        many_attachment_row.addWidget(self.many_file)
        many_attachment_row.addWidget(many_file_button)
        many_form.addRow("Attachment", many_attachment_row)
        many_form.addRow("Delay between groups (s)", self.many_delay)
        many_form.addRow(many_send)
        many_form.addRow(self.many_status)
        tabs.addTab(many, "Many managed groups")

        users = QWidget()
        user_form = QFormLayout(users)
        self.user_account = AccountCombo(db)
        self.user_source = QComboBox()
        self.user_offset = QSpinBox()
        self.user_offset.setRange(0, 1_000_000)
        self.user_text = QTextEdit()
        self.user_file = QLineEdit()
        user_file_button = QPushButton("Choose file")
        user_file_button.clicked.connect(lambda: self._choose_file(self.user_file))
        self.user_limit = QSpinBox()
        self.user_limit.setRange(1, 500)
        self.user_limit.setValue(20)
        self.user_status = QLabel()
        user_send = QPushButton("Send to opted-in users")
        user_send.clicked.connect(self.send_users)
        user_form.addRow("Account", self.user_account)
        user_form.addRow("Source", self.user_source)
        user_form.addRow("Start offset", self.user_offset)
        user_form.addRow("Message", self.user_text)
        user_attachment_row = QHBoxLayout()
        user_attachment_row.addWidget(self.user_file)
        user_attachment_row.addWidget(user_file_button)
        user_form.addRow("Attachment", user_attachment_row)
        user_form.addRow("Limit", self.user_limit)
        user_form.addRow(user_send)
        user_form.addRow(self.user_status)
        tabs.addTab(users, "Opted-in users")
        self.reload_sources()

    @staticmethod
    def _choose_file(target: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(None, "Choose attachment")
        if path:
            target.setText(path)

    def reload_sources(self) -> None:
        current = self.user_source.currentData()
        self.user_source.clear()
        self.user_source.addItem("All sources", None)
        for source in self.db.member_sources():
            self.user_source.addItem(source, source)
        if current is not None:
            index = self.user_source.findData(current)
            if index >= 0:
                self.user_source.setCurrentIndex(index)

    def send_group(self) -> None:
        account_id = self.group_account.currentData()
        if account_id is None:
            return

        async def factory(_progress):
            return await self.service.send_group(
                int(account_id), self.group_target.text().strip(), self.group_text.toPlainText(), self.group_file.text().strip()
            )

        task = AsyncTask(factory)
        task.signals.result.connect(lambda _result: QMessageBox.information(self, "Message", "Sent"))
        task.signals.error.connect(lambda error: QMessageBox.critical(self, "Message failed", error))
        self.pool.start(task)

    def send_many_groups(self) -> None:
        account_id = self.many_account.currentData()
        if account_id is None:
            return
        targets = self.many_targets.toPlainText().splitlines()

        async def factory(progress):
            return await self.service.send_managed_groups(
                int(account_id), targets, self.many_text.toPlainText(), self.many_file.text().strip(),
                self.many_delay.value(), progress,
            )

        task = AsyncTask(factory)
        task.signals.progress.connect(lambda i, n, text: self.many_status.setText(f"{i}/{n}: {text}"))
        task.signals.result.connect(
            lambda result: self.many_status.setText(
                f"Success={result.success} Failed={result.failed} {result.stopped_reason}"
            )
        )
        task.signals.error.connect(lambda error: QMessageBox.critical(self, "Broadcast failed", error))
        self.pool.start(task)

    def send_users(self) -> None:
        account_id = self.user_account.currentData()
        if account_id is None:
            return
        try:
            delay_min = float(self.db.get_setting("message_delay_min", "8"))
            delay_max = float(self.db.get_setting("message_delay_max", "15"))
        except ValueError:
            QMessageBox.warning(self, "Settings", "Message delay settings must be numbers")
            return

        async def factory(progress):
            return await self.service.send_opted_in(
                int(account_id), self.user_text.toPlainText(), self.user_limit.value(), delay_min, delay_max,
                progress, self.user_source.currentData(), self.user_offset.value(), self.user_file.text().strip(),
            )

        task = AsyncTask(factory)
        task.signals.progress.connect(lambda i, n, text: self.user_status.setText(f"{i}/{n}: {text}"))
        task.signals.result.connect(
            lambda result: self.user_status.setText(
                f"Success={result.success} Failed={result.failed} {result.stopped_reason}"
            )
        )
        task.signals.error.connect(lambda error: QMessageBox.critical(self, "Campaign failed", error))
        self.pool.start(task)


class JoinTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.service = JoinService(db)
        self.pool = QThreadPool.globalInstance()
        form = QFormLayout(self)
        self.account = AccountCombo(db)
        self.group = QLineEdit()
        join = QPushButton("Join with selected account")
        leave = QPushButton("Leave with selected account")
        join.clicked.connect(lambda: self.run(True))
        leave.clicked.connect(lambda: self.run(False))
        self.status = QLabel()
        form.addRow("Account", self.account)
        form.addRow("Group/channel", self.group)
        form.addRow(join)
        form.addRow(leave)
        form.addRow(self.status)

    def run(self, is_join: bool) -> None:
        account_id = self.account.currentData()
        if account_id is None:
            return

        async def factory(_progress):
            if is_join:
                return await self.service.join(int(account_id), self.group.text().strip())
            await self.service.leave(int(account_id), self.group.text().strip())
            return ""

        task = AsyncTask(factory)
        task.signals.result.connect(lambda result: self.status.setText("Success" + (f": {result}" if result else "")))
        task.signals.error.connect(lambda error: QMessageBox.critical(self, "Join/Leave failed", error))
        self.pool.start(task)


class ProxyPoolTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        buttons = QHBoxLayout()
        add = QPushButton("Add proxy")
        add.clicked.connect(self.add_proxy)
        import_button = QPushButton("Import proxy file")
        import_button.clicked.connect(self.import_proxies)
        delete = QPushButton("Delete selected")
        delete.clicked.connect(self.delete_proxy)
        toggle = QPushButton("Enable/disable selected")
        toggle.clicked.connect(self.toggle_proxy)
        assign = QPushButton("Assign selected to account")
        assign.clicked.connect(self.assign)
        unassign = QPushButton("Unassign account proxy")
        unassign.clicked.connect(self.unassign)
        for button in (add, import_button, delete, toggle, assign, unassign):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.account = AccountCombo(db)
        layout.addWidget(self.account)
        self.table = QTableWidget()
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        table_set(self.table, self.db.proxies(), ["id", "proxy_type", "host", "port", "username", "label", "enabled"])

    def add_proxy(self) -> None:
        text, ok = QInputDialog.getText(self, "Proxy", "type,host,port,user,password,label")
        if not ok:
            return
        try:
            parts = [part.strip() for part in text.split(",")]
            if len(parts) < 3:
                raise ValueError("Expected at least type,host,port")
            parts += [""] * (6 - len(parts))
            proxy_id = self.db.add_proxy(parts[0] or "socks5", parts[1], int(parts[2]), parts[3], parts[5])
            credentials.set_proxy_password(proxy_id, parts[4])
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Proxy", str(exc))

    def import_proxies(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import proxies", "", "Text/CSV (*.txt *.csv);;All files (*)")
        if not path:
            return
        success = 0
        errors: list[str] = []
        with open(path, "r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                try:
                    parts = next(csv.reader([line]))
                    parts = [part.strip() for part in parts] + [""] * 6
                    proxy_id = self.db.add_proxy(parts[0] or "socks5", parts[1], int(parts[2]), parts[3], parts[5])
                    credentials.set_proxy_password(proxy_id, parts[4])
                    success += 1
                except Exception as exc:
                    errors.append(f"line {line_number}: {exc}")
        self.refresh()
        message = f"Imported {success} proxies"
        if errors:
            message += "\n" + "\n".join(errors[:10])
        QMessageBox.information(self, "Proxy import", message)

    def delete_proxy(self) -> None:
        proxy_id = selected_id(self.table)
        if proxy_id is None:
            return
        try:
            credentials.delete_proxy_password(proxy_id)
        except Exception:
            # Deleting the database record should not be blocked by an unavailable
            # credential backend. Stale OS credentials can be removed later.
            pass
        self.db.delete_proxy(proxy_id)
        self.refresh()

    def toggle_proxy(self) -> None:
        proxy_id = selected_id(self.table)
        if proxy_id is None:
            return
        proxy = self.db.proxy(proxy_id)
        self.db.set_proxy_enabled(proxy_id, not bool(proxy["enabled"]))
        self.refresh()

    def assign(self) -> None:
        proxy_id = selected_id(self.table)
        account_id = self.account.currentData()
        if proxy_id is None or account_id is None:
            return
        try:
            self.db.assign_proxy(int(account_id), proxy_id)
            QMessageBox.information(self, "Proxy", "Assigned. The change takes effect on the next connection.")
        except Exception as exc:
            QMessageBox.warning(self, "Proxy", str(exc))

    def unassign(self) -> None:
        account_id = self.account.currentData()
        if account_id is not None:
            self.db.assign_proxy(int(account_id), None)
            QMessageBox.information(self, "Proxy", "Proxy unassigned")


class ArchiveScriptTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.archive = MessageArchiveService(db)
        self.script = ScriptService(db)
        self.pool = QThreadPool.globalInstance()
        self.archive_rows: list[dict] = []
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        archive_widget = QWidget()
        archive_layout = QVBoxLayout(archive_widget)
        top = QHBoxLayout()
        self.archive_account = AccountCombo(db)
        self.archive_group = QLineEdit()
        self.archive_limit = QSpinBox()
        self.archive_limit.setRange(1, 100000)
        self.archive_limit.setValue(int(db.get_setting("archive_limit", "200")))
        self.download_media = QCheckBox("Download media")
        self.media_dir = QLineEdit()
        choose_media = QPushButton("Media folder")
        choose_media.clicked.connect(self.choose_media_dir)
        run = QPushButton("Archive managed group")
        run.clicked.connect(self.run_archive)
        save = QPushButton("Export archive CSV")
        save.clicked.connect(self.export_archive)
        for widget in (
            self.archive_account, self.archive_group, self.archive_limit, self.download_media,
            self.media_dir, choose_media, run, save,
        ):
            top.addWidget(widget)
        archive_layout.addLayout(top)
        self.archive_status = QLabel()
        archive_layout.addWidget(self.archive_status)
        self.archive_table = QTableWidget()
        archive_layout.addWidget(self.archive_table)
        tabs.addTab(archive_widget, "Get messages")

        script_widget = QWidget()
        script_form = QFormLayout(script_widget)
        self.script_account = AccountCombo(db)
        self.script_target = QLineEdit()
        self.script_repeat = QSpinBox()
        self.script_repeat.setRange(1, 20)
        self.script_repeat.setValue(1)
        self.script_text = QTextEdit()
        self.script_text.setPlaceholderText(
            "One step per line: delay_seconds | reply_to_index | file_path | text\n"
            "Example:\n0|||Hello team\n2|0||Reply to first message"
        )
        run_script = QPushButton("Run managed script")
        run_script.clicked.connect(self.run_script)
        self.script_status = QLabel()
        script_form.addRow("Account", self.script_account)
        script_form.addRow("Managed group", self.script_target)
        script_form.addRow("Repeat", self.script_repeat)
        script_form.addRow("Script", self.script_text)
        script_form.addRow(run_script)
        script_form.addRow(self.script_status)
        tabs.addTab(script_widget, "Seeding / Script")

    def choose_media_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Media folder")
        if path:
            self.media_dir.setText(path)

    def run_archive(self) -> None:
        account_id = self.archive_account.currentData()
        if account_id is None:
            return

        async def factory(progress):
            return await self.archive.archive_managed(
                int(account_id), self.archive_group.text().strip(), self.archive_limit.value(),
                self.download_media.isChecked(), self.media_dir.text().strip(), progress,
            )

        task = AsyncTask(factory)
        task.signals.progress.connect(lambda i, n, text: self.archive_status.setText(f"{i}/{n}: {text}"))
        task.signals.result.connect(self.archive_done)
        task.signals.error.connect(lambda error: QMessageBox.critical(self, "Archive failed", error))
        self.pool.start(task)

    def archive_done(self, rows: list[dict]) -> None:
        self.archive_rows = rows
        self.archive_status.setText(f"Archived {len(rows)} messages")
        table_set(
            self.archive_table,
            rows,
            ["message_id", "sender_id", "date", "reply_to_message_id", "has_media", "media_type", "saved_media", "text"],
        )

    def export_archive(self) -> None:
        if not self.archive_rows:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export archive", "messages.csv", "CSV (*.csv)")
        if not path:
            return
        keys = ["message_id", "sender_id", "date", "reply_to_message_id", "has_media", "media_type", "saved_media", "text"]
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys)
            writer.writeheader()
            writer.writerows(self.archive_rows)

    def run_script(self) -> None:
        account_id = self.script_account.currentData()
        if account_id is None:
            return
        steps: list[dict] = []
        try:
            for line_number, line in enumerate(self.script_text.toPlainText().splitlines(), 1):
                if not line.strip():
                    continue
                parts = line.split("|", 3)
                parts += [""] * (4 - len(parts))
                delay = float(parts[0] or 0)
                if delay < 0:
                    raise ValueError(f"Line {line_number}: delay cannot be negative")
                reply = int(parts[1]) if parts[1].strip() else None
                if reply is not None and (reply < 0 or reply >= len(steps)):
                    raise ValueError(
                        f"Line {line_number}: reply_to_index must reference an earlier 0-based step"
                    )
                steps.append({"delay": delay, "reply_to_index": reply, "file": parts[2].strip(), "text": parts[3]})
        except Exception as exc:
            QMessageBox.warning(self, "Script", str(exc))
            return
        if not steps:
            QMessageBox.warning(self, "Script", "Script is empty")
            return

        async def factory(progress):
            return await self.script.run_managed_sequence(
                int(account_id), self.script_target.text().strip(), steps, self.script_repeat.value(), progress,
            )

        task = AsyncTask(factory)
        task.signals.progress.connect(lambda i, n, text: self.script_status.setText(f"{i}/{n}: {text}"))
        task.signals.result.connect(
            lambda result: self.script_status.setText(
                f"Success={result.success} Failed={result.failed} Skipped={result.skipped} {result.stopped_reason}"
            )
        )
        task.signals.error.connect(lambda error: QMessageBox.critical(self, "Script failed", error))
        self.pool.start(task)


class LogsTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)
        self.table = QTableWidget()
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        table_set(
            self.table,
            self.db.logs(),
            ["id", "created_at", "action_type", "account_phone", "target", "user_id", "username", "outcome", "error_code", "detail"],
        )


class SettingsTab(QWidget):
    NUMERIC_KEYS = {
        "invite_delay_min": float,
        "invite_delay_max": float,
        "message_delay_min": float,
        "message_delay_max": float,
        "daily_invite_cap": int,
        "campaign_limit": int,
        "scan_limit": int,
        "archive_limit": int,
    }

    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        form = QFormLayout(self)
        self.fields: dict[str, QLineEdit] = {}
        labels = [
            ("invite_delay_min", "Invite delay min (s)"),
            ("invite_delay_max", "Invite delay max (s)"),
            ("message_delay_min", "Message delay min (s)"),
            ("message_delay_max", "Message delay max (s)"),
            ("daily_invite_cap", "Daily invite cap / account"),
            ("campaign_limit", "Campaign default limit"),
            ("scan_limit", "Default scan limit"),
            ("archive_limit", "Default archive limit"),
            ("update_manifest_url", "Update manifest HTTPS URL"),
        ]
        for key, label in labels:
            field = QLineEdit(self.db.get_setting(key, ""))
            self.fields[key] = field
            form.addRow(label, field)
        save = QPushButton("Save settings")
        save.clicked.connect(self.save)
        form.addRow(save)

    def save(self) -> None:
        try:
            values = {key: field.text().strip() for key, field in self.fields.items()}
            for key, converter in self.NUMERIC_KEYS.items():
                value = converter(values[key])
                if value < 0:
                    raise ValueError(f"{key} cannot be negative")
            if float(values["invite_delay_max"]) < float(values["invite_delay_min"]):
                raise ValueError("invite_delay_max must be >= invite_delay_min")
            if float(values["message_delay_max"]) < float(values["message_delay_min"]):
                raise ValueError("message_delay_max must be >= message_delay_min")
            update_url = values["update_manifest_url"]
            if update_url and not update_url.lower().startswith("https://"):
                raise ValueError("Update manifest URL must use HTTPS")
            for key, value in values.items():
                self.db.set_setting(key, value)
            QMessageBox.information(self, "Settings", "Saved")
        except Exception as exc:
            QMessageBox.warning(self, "Settings", str(exc))


class LicenseUpdateTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.pool = QThreadPool.globalInstance()
        self.last_manifest: dict | None = None
        layout = QVBoxLayout(self)
        buttons = QHBoxLayout()
        license_button = QPushButton("Inspect local license JSON")
        license_button.clicked.connect(self.license)
        check_button = QPushButton("Check update manifest")
        check_button.clicked.connect(self.update)
        download_button = QPushButton("Download verified update")
        download_button.clicked.connect(self.download_update)
        buttons.addWidget(license_button)
        buttons.addWidget(check_button)
        buttons.addWidget(download_button)
        layout.addLayout(buttons)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)

    def license(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "License", "", "JSON (*.json)")
        if path:
            self.output.setPlainText(str(read_license(path)))

    def update(self) -> None:
        url = self.db.get_setting("update_manifest_url", "")

        async def factory(_progress):
            return await __import__("asyncio").to_thread(check_update, url)

        task = AsyncTask(factory)
        task.signals.result.connect(self._update_result)
        task.signals.error.connect(lambda error: self.output.setPlainText(error))
        self.pool.start(task)

    def _update_result(self, result: dict) -> None:
        self.last_manifest = result
        self.output.setPlainText(str(result))

    def download_update(self) -> None:
        if not self.last_manifest or not self.last_manifest.get("update_available"):
            QMessageBox.information(self, "Update", "No newer verified manifest is loaded")
            return
        ensure_dirs()
        url = str(self.last_manifest["url"])
        digest = str(self.last_manifest["sha256"])
        name = Path(url.split("?", 1)[0]).name or f"TelegramOpsStudio-{self.last_manifest['version']}.exe"
        destination = str(DOWNLOADS_DIR / name)

        async def factory(_progress):
            return await __import__("asyncio").to_thread(download_verified, url, digest, destination)

        task = AsyncTask(factory)
        task.signals.result.connect(
            lambda result: self.output.setPlainText(f"Downloaded and verified:\n{destination}\nSHA-256: {result}")
        )
        task.signals.error.connect(lambda error: self.output.setPlainText(error))
        self.pool.start(task)


class MainWindow(QMainWindow):
    def __init__(self, db: Database | None = None):
        super().__init__()
        ensure_dirs()
        self.db = db or Database()
        self.setWindowTitle(f"{APP_DISPLAY_NAME} {APP_VERSION}")
        self.resize(1380, 860)
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        self.dashboard = DashboardTab(self.db)
        self.accounts = AccountsTab(self.db)
        self.scanner = ScannerTab(self.db)
        self.filter = FilterTab(self.db)
        self.invite = InviteTab(self.db)
        self.messaging = MessengerTab(self.db)
        self.join = JoinTab(self.db)
        self.proxies = ProxyPoolTab(self.db)
        self.archive_script = ArchiveScriptTab(self.db)
        self.logs = LogsTab(self.db)
        self.settings = SettingsTab(self.db)
        self.license_update = LicenseUpdateTab(self.db)

        widgets = [
            (self.dashboard, "Dashboard"),
            (self.accounts, "Accounts & Sessions"),
            (self.scanner, "Scanner"),
            (self.filter, "Filter & Consent"),
            (self.invite, "Invite Queue"),
            (self.messaging, "Messaging"),
            (self.join, "Join / Leave"),
            (self.proxies, "Proxy Pool"),
            (self.archive_script, "Get Messages / Seeding"),
            (self.logs, "Logs"),
            (self.settings, "Settings"),
            (self.license_update, "License / Update"),
        ]
        for widget, name in widgets:
            tabs.addTab(widget, name)
        tabs.currentChanged.connect(self._refresh_dynamic_controls)

    def _refresh_dynamic_controls(self, _index: int) -> None:
        for combo in self.findChildren(AccountCombo):
            combo.reload()
        self.dashboard.refresh()
        self.logs.refresh()
        self.filter.reload_sources()
        self.invite.reload_sources()
        self.messaging.reload_sources()
