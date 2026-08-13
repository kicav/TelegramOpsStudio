from __future__ import annotations

import asyncio
import json
import re
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from telegram_workflow.accounts.manager import AccountManager
from telegram_workflow.diagnostics.paths import ensure_runtime_dirs
from telegram_workflow.domain.commands import (
    CheckAccountSessionCommand,
    Command,
    CreateReviewJobCommand,
    ExportMembersCommand,
    PingCommand,
    PreviewWorkflowCommand,
    RefreshAccountsCommand,
    RefreshDashboardCommand,
    RefreshGroupsCommand,
    RefreshJobsCommand,
    RefreshLogsCommand,
    RefreshMembersCommand,
    RequestLoginCodeCommand,
    ScanSourceCommand,
    ShutdownCommand,
    SubmitLoginCodeCommand,
    SubmitLoginPasswordCommand,
    UpdateMemberConsentCommand,
)
from telegram_workflow.domain.enums import AccountState, JobState, SnapshotState
from telegram_workflow.domain.events import (
    AccountSessionCheckedEvent,
    AccountsUpdatedEvent,
    AuthCodeRequestedEvent,
    AuthPasswordRequiredEvent,
    AuthSucceededEvent,
    DashboardUpdatedEvent,
    ExportCompletedEvent,
    GroupsUpdatedEvent,
    JobsUpdatedEvent,
    LogsUpdatedEvent,
    MemberConsentUpdatedEvent,
    MembersUpdatedEvent,
    PongEvent,
    ReviewJobCreatedEvent,
    RuntimeReadyEvent,
    RuntimeStoppedEvent,
    SourceScanCompletedEvent,
    SourceScanProgressEvent,
    SystemErrorEvent,
    WorkflowPreviewEvent,
)
from telegram_workflow.domain.models import AuditEntry, ScanProgress
from telegram_workflow.exports.exporter import ResultExporter
from telegram_workflow.jobs.builder import JobBuilder
from telegram_workflow.jobs.candidate_builder import CandidateBuilder
from telegram_workflow.security.secret_store import KeyringSecretStore
from telegram_workflow.storage.database import Database
from telegram_workflow.storage.repositories.accounts import AccountRepository
from telegram_workflow.storage.repositories.api_profiles import ApiProfileRepository
from telegram_workflow.storage.repositories.audit import AuditRepository
from telegram_workflow.storage.repositories.jobs import JobRepository
from telegram_workflow.storage.repositories.members import MemberRepository
from telegram_workflow.storage.repositories.sources import SourceRepository
from telegram_workflow.storage.repositories.targets import TargetRepository
from telegram_workflow.telegram.auth_service import TelethonAuthService
from telegram_workflow.telegram.source_scanner import SourceScanner
from telegram_workflow.telegram.target_validator import TargetValidator
from telegram_workflow.telegram.telethon_adapter import TelethonReadOnlyAdapter


@dataclass(slots=True)
class _PendingAuth:
    account_id: int
    phone: str
    service: TelethonAuthService
    phone_code_hash: str


class CoreRuntime(QThread):
    """Background owner of asyncio, Telegram clients, keyring access and SQLite writes."""

    event_emitted = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[Command] | None = None
        self._stop_requested = threading.Event()
        self._database: Database | None = None
        self._paths: dict[str, Path] = {}
        self._secrets = KeyringSecretStore()
        self._pending_auth: dict[str, _PendingAuth] = {}

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
            self._paths = ensure_runtime_dirs()
            self._database = Database(self._paths["data"] / "app.db")
            self._database.open()
            self._database.migrate()
            self.event_emitted.emit(RuntimeReadyEvent())
            self._emit_dashboard()
            self._emit_accounts()
            if self._stop_requested.is_set():
                return
            while True:
                command = await self._queue.get()
                if isinstance(command, ShutdownCommand):
                    break
                try:
                    await self._handle(command)
                except Exception as exc:
                    self.event_emitted.emit(
                        SystemErrorEvent(message=f"{type(exc).__name__}: {exc}")
                    )
        except Exception as exc:
            self.event_emitted.emit(
                SystemErrorEvent(message=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            )
        finally:
            for pending in list(self._pending_auth.values()):
                await pending.service.close()
            self._pending_auth.clear()
            if self._database is not None:
                self._database.close()
            self._database = None
            self.event_emitted.emit(RuntimeStoppedEvent())
            self._queue = None
            self._loop = None

    @property
    def _connection(self):
        if self._database is None:
            raise RuntimeError("Database is not ready")
        return self._database.open()

    async def _handle(self, command: Command) -> None:
        if isinstance(command, PingCommand):
            self.event_emitted.emit(
                PongEvent(command_id=command.command_id, payload=command.payload)
            )
        elif isinstance(command, RefreshDashboardCommand):
            self._emit_dashboard()
        elif isinstance(command, RefreshAccountsCommand):
            self._emit_accounts()
        elif isinstance(command, RequestLoginCodeCommand):
            await self._request_login_code(command)
        elif isinstance(command, SubmitLoginCodeCommand):
            await self._submit_login_code(command)
        elif isinstance(command, SubmitLoginPasswordCommand):
            await self._submit_login_password(command)
        elif isinstance(command, CheckAccountSessionCommand):
            await self._check_account_session(command)
        elif isinstance(command, ScanSourceCommand):
            await self._scan_source(command)
        elif isinstance(command, PreviewWorkflowCommand):
            await self._preview_workflow(command)
        elif isinstance(command, CreateReviewJobCommand):
            self._create_review_job(command)
        elif isinstance(command, ExportMembersCommand):
            self._export_members(command)
        elif isinstance(command, RefreshJobsCommand):
            self._emit_jobs()
        elif isinstance(command, RefreshLogsCommand):
            self._emit_logs(command.limit)
        elif isinstance(command, RefreshGroupsCommand):
            self._emit_groups(command.limit)
        elif isinstance(command, RefreshMembersCommand):
            self._emit_members(command)
        elif isinstance(command, UpdateMemberConsentCommand):
            self._update_member_consent(command)

    def _audit(self, event_type: str, **details: object) -> None:
        AuditRepository(self._connection).append(
            AuditEntry(event_type=event_type, details=details)
        )

    def _emit_dashboard(self) -> None:
        accounts = AccountRepository(self._connection)
        jobs = JobRepository(self._connection)
        members = MemberRepository(self._connection)
        self.event_emitted.emit(
            DashboardUpdatedEvent(
                accounts_ready=accounts.count_by_state(AccountState.READY),
                jobs_running=jobs.counts_by_state(JobState.RUNNING),
                jobs_paused=jobs.counts_by_state(JobState.PAUSED),
                members_total=members.count(),
            )
        )

    def _emit_accounts(self) -> None:
        rows = AccountRepository(self._connection).list_all()
        payload = tuple(
            {
                "id": int(row["id"]),
                "phone": row["phone"],
                "username": row["username"] or "",
                "state": row["state"],
                "profile": row["api_profile_name"] or "",
                "session_ref": row["session_ref"] or "",
            }
            for row in rows
        )
        self.event_emitted.emit(AccountsUpdatedEvent(accounts=payload))

    @staticmethod
    def _session_name(phone: str) -> str:
        cleaned = re.sub(r"[^0-9+]", "", phone).replace("+", "plus_")
        return cleaned or "account"

    async def _request_login_code(self, command: RequestLoginCodeCommand) -> None:
        profile_name = command.profile_name.strip() or "Default"
        phone = command.phone.strip()
        api_hash = command.api_hash.strip()
        if not phone or command.api_id <= 0 or not api_hash:
            raise ValueError("API ID, API Hash and phone are required")
        secret_ref = f"api-profile:{profile_name}:api-hash"
        self._secrets.set(secret_ref, api_hash)
        profile_id = ApiProfileRepository(self._connection).upsert(
            name=profile_name, api_id=command.api_id, api_hash_secret_ref=secret_ref
        )
        session_path = self._paths["sessions"] / self._session_name(phone)
        manager = AccountManager(self._connection)
        account_id = manager.register(
            phone=phone, session_path=session_path, api_profile_id=profile_id
        )
        service = TelethonAuthService(
            session_path=session_path, api_id=command.api_id, api_hash=api_hash
        )
        await service.connect()
        if await service.is_authorized():
            AccountRepository(self._connection).set_state(account_id, AccountState.READY)
            await service.close()
            self._audit("AUTH_ALREADY_READY", account_id=account_id, phone=phone)
            self.event_emitted.emit(AuthSucceededEvent(account_id=account_id, phone=phone))
        else:
            code_hash = await service.request_code(phone)
            old = self._pending_auth.pop(phone, None)
            if old is not None:
                await old.service.close()
            self._pending_auth[phone] = _PendingAuth(account_id, phone, service, code_hash)
            AccountRepository(self._connection).set_state(account_id, AccountState.AUTH_REQUIRED)
            self._audit("AUTH_CODE_REQUESTED", account_id=account_id, phone=phone)
            self.event_emitted.emit(AuthCodeRequestedEvent(account_id=account_id, phone=phone))
        self._emit_accounts()
        self._emit_dashboard()

    async def _submit_login_code(self, command: SubmitLoginCodeCommand) -> None:
        pending = self._pending_auth.get(command.phone.strip())
        if pending is None:
            raise ValueError("No pending login for this phone; request a new code")
        signed_in = await pending.service.sign_in_code(
            phone=pending.phone,
            code=command.code.strip(),
            phone_code_hash=pending.phone_code_hash,
        )
        if not signed_in:
            self.event_emitted.emit(
                AuthPasswordRequiredEvent(account_id=pending.account_id, phone=pending.phone)
            )
            return
        await self._finish_auth(pending)

    async def _submit_login_password(self, command: SubmitLoginPasswordCommand) -> None:
        pending = self._pending_auth.get(command.phone.strip())
        if pending is None:
            raise ValueError("No pending 2FA login for this phone")
        await pending.service.sign_in_password(command.password)
        await self._finish_auth(pending)

    async def _finish_auth(self, pending: _PendingAuth) -> None:
        AccountRepository(self._connection).set_state(pending.account_id, AccountState.READY)
        await pending.service.close()
        self._pending_auth.pop(pending.phone, None)
        self._audit("AUTH_SUCCEEDED", account_id=pending.account_id, phone=pending.phone)
        self.event_emitted.emit(
            AuthSucceededEvent(account_id=pending.account_id, phone=pending.phone)
        )
        self._emit_accounts()
        self._emit_dashboard()

    def _account_adapter(self, account_id: int) -> TelethonReadOnlyAdapter:
        row = AccountRepository(self._connection).get_with_profile(account_id)
        if row is None:
            raise ValueError("Account not found")
        if row["state"] != AccountState.READY.value:
            raise ValueError("Account is not READY")
        secret_ref = row["api_hash_secret_ref"]
        if not secret_ref or not row["api_id"] or not row["session_ref"]:
            raise ValueError("Account API/session configuration is incomplete")
        api_hash = self._secrets.get(str(secret_ref))
        if not api_hash:
            raise ValueError("API Hash is unavailable in the OS credential store")
        return TelethonReadOnlyAdapter(
            session_path=Path(row["session_ref"]),
            api_id=int(row["api_id"]),
            api_hash=api_hash,
        )

    @staticmethod
    def _row_to_member(row) -> dict[str, object]:
        return {
            "id": int(row["id"]),
            "user_id": int(row["telegram_user_id"]),
            "username": row["username"] or "",
            "first_name": row["first_name"] or "",
            "last_name": row["last_name"] or "",
            "phone": row["phone"] or "",
            "is_bot": bool(row["is_bot"]),
            "is_deleted": bool(row["is_deleted"]),
            "last_seen": row["last_seen"] or "",
            "activity_quality": row["activity_quality"] or "UNKNOWN",
            "consent_state": row["consent_state"] if "consent_state" in row.keys() else "UNKNOWN",
            "notes": row["notes"] if "notes" in row.keys() else "",
        }

    def _emit_groups(self, limit: int = 1000) -> None:
        rows = SourceRepository(self._connection).list_all(limit)
        payload = tuple(
            {
                "id": int(row["id"]),
                "identifier": row["input_identifier"],
                "entity_id": row["telegram_entity_id"] or "",
                "title": row["title"] or "",
                "username": row["username"] or "",
                "entity_type": row["entity_type"] or "",
                "scan_state": row["scan_state"],
                "members": int(row["scanned_member_count"] or 0),
                "started": row["last_scan_started"] or "",
                "finished": row["last_scan_finished"] or "",
                "error": row["scan_error"] or "",
            }
            for row in rows
        )
        self.event_emitted.emit(GroupsUpdatedEvent(groups=payload))

    def _emit_members(self, command: RefreshMembersCommand) -> None:
        rows, total = MemberRepository(self._connection).list_rows(
            search=command.search,
            consent_state=command.consent_state,
            source_id=command.source_id,
            limit=command.limit,
        )
        payload = tuple(self._row_to_member(row) for row in rows)
        self.event_emitted.emit(
            MembersUpdatedEvent(
                members=payload, total=total, truncated=total > len(payload)
            )
        )

    def _update_member_consent(self, command: UpdateMemberConsentCommand) -> None:
        updated = MemberRepository(self._connection).set_consent(
            list(command.member_ids), command.consent_state, notes=command.notes
        )
        self._audit(
            "MEMBER_CONSENT_UPDATED",
            member_ids=list(command.member_ids),
            consent_state=command.consent_state,
            updated=updated,
        )
        self.event_emitted.emit(
            MemberConsentUpdatedEvent(
                updated=updated, consent_state=command.consent_state.strip().upper()
            )
        )
        self._emit_dashboard()

    async def _check_account_session(self, command: CheckAccountSessionCommand) -> None:
        adapter = self._account_adapter(command.account_id)
        try:
            healthy = await adapter.health_check()
            AccountRepository(self._connection).set_state(
                command.account_id,
                AccountState.READY if healthy else AccountState.AUTH_REQUIRED,
            )
            self._audit(
                "ACCOUNT_SESSION_CHECKED", account_id=command.account_id, healthy=healthy
            )
            self.event_emitted.emit(
                AccountSessionCheckedEvent(account_id=command.account_id, healthy=healthy)
            )
            self._emit_accounts()
            self._emit_dashboard()
        finally:
            await adapter.close()

    async def _scan_source(self, command: ScanSourceCommand) -> None:
        identifier = command.identifier.strip()
        if not identifier:
            raise ValueError("Source identifier is required")
        adapter = self._account_adapter(command.account_id)
        source_id = SourceRepository(self._connection).create(identifier)
        scanner = SourceScanner(self._connection, adapter)
        try:
            def progress(item: ScanProgress) -> None:
                self.event_emitted.emit(
                    SourceScanProgressEvent(
                        source_id=source_id, persisted=item.persisted, finished=item.finished
                    )
                )

            total = await scanner.scan(
                source_id=source_id, identifier=identifier, on_progress=progress
            )
            rows = SourceRepository(self._connection).member_rows(source_id)
            limit = 5000
            payload = tuple(self._row_to_member(row) for row in rows[:limit])
            self._audit(
                "SOURCE_SCAN_COMPLETED",
                source_id=source_id,
                account_id=command.account_id,
                total=total,
            )
            self.event_emitted.emit(
                SourceScanCompletedEvent(
                    source_id=source_id,
                    total=total,
                    members=payload,
                    truncated=len(rows) > limit,
                )
            )
            self._emit_dashboard()
            self._emit_groups()
            self._emit_members(RefreshMembersCommand(source_id=source_id))
        finally:
            await adapter.close()

    async def _preview_workflow(self, command: PreviewWorkflowCommand) -> None:
        if command.source_id <= 0:
            raise ValueError("Scan a source first")
        identifier = command.target_identifier.strip()
        if not identifier:
            raise ValueError("Target identifier is required")
        adapter = self._account_adapter(command.account_id)
        targets = TargetRepository(self._connection)
        target_id = targets.create(identifier)
        validator = TargetValidator(self._connection, adapter)
        try:
            entity, validation = await validator.validate(
                target_id=target_id, identifier=identifier
            )
            snapshot_id = await validator.capture_snapshot(
                target_id=target_id, entity=entity
            )
            member_ids, preview = CandidateBuilder(self._connection).build(
                source_id=command.source_id,
                target_id=target_id,
                target_snapshot_id=snapshot_id,
                config=command.filter_config,
                max_items=command.max_items,
            )
            snapshot = self._connection.execute(
                "SELECT snapshot_state, error_message FROM target_snapshots WHERE id = ?",
                (snapshot_id,),
            ).fetchone()
            if snapshot is None or snapshot["snapshot_state"] != SnapshotState.COMPLETE.value:
                reason = snapshot["error_message"] if snapshot is not None else "snapshot missing"
                self._audit(
                    "TARGET_SNAPSHOT_UNAVAILABLE",
                    target_id=target_id,
                    snapshot_id=snapshot_id,
                    reason=reason or "participant list unavailable",
                )
                raise ValueError(
                    "Target participant snapshot is unavailable; candidate subtraction cannot "
                    "be verified safely."
                )
            limit = 5000
            selected_ids = member_ids[:limit]
            if selected_ids:
                placeholders = ",".join("?" for _ in selected_ids)
                rows = self._connection.execute(
                    f"SELECT * FROM members WHERE id IN ({placeholders}) ORDER BY id",
                    selected_ids,
                ).fetchall()
            else:
                rows = []
            self._audit(
                "WORKFLOW_PREVIEW",
                source_id=command.source_id,
                target_id=target_id,
                snapshot_id=snapshot_id,
                candidates=preview.candidates,
                selected=preview.selected,
                permission_state=validation.permission_state,
            )
            self.event_emitted.emit(
                WorkflowPreviewEvent(
                    target_id=target_id,
                    target_snapshot_id=snapshot_id,
                    target_title=entity.title,
                    permission_state=validation.permission_state,
                    snapshot_state=snapshot["snapshot_state"] if snapshot else "UNKNOWN",
                    preview=preview,
                    members=tuple(self._row_to_member(row) for row in rows),
                    selected_member_ids=tuple(member_ids),
                    truncated=len(member_ids) > limit,
                )
            )
        finally:
            await adapter.close()

    def _create_review_job(self, command: CreateReviewJobCommand) -> None:
        job_id, preview = JobBuilder(self._connection).create_job(
            name=command.name.strip() or "Review job",
            source_id=command.source_id,
            target_id=command.target_id,
            target_snapshot_id=command.target_snapshot_id,
            filter_config=command.filter_config,
            selected_accounts=[command.account_id] if command.account_id else [],
            max_items=command.max_items,
        )
        self._audit("REVIEW_JOB_CREATED", job_id=job_id, selected=preview.selected)
        self.event_emitted.emit(ReviewJobCreatedEvent(job_id=job_id, selected=preview.selected))
        self._emit_jobs()

    def _export_members(self, command: ExportMembersCommand) -> None:
        if not command.member_ids:
            raise ValueError("There are no preview members to export")
        exporter = ResultExporter(self._connection)
        path = Path(command.path)
        fmt = command.file_format.casefold()
        if fmt == "csv":
            rows = exporter.export_members_csv(list(command.member_ids), path)
        elif fmt == "xlsx":
            rows = exporter.export_members_xlsx(list(command.member_ids), path)
        else:
            raise ValueError("Unsupported export format")
        self._audit("MEMBERS_EXPORTED", path=str(path), rows=rows, format=fmt)
        self.event_emitted.emit(ExportCompletedEvent(path=str(path), rows=rows, file_format=fmt))

    def _emit_jobs(self) -> None:
        rows = self._connection.execute(
            """
            SELECT j.id, j.name, j.state, j.total, j.success, j.skipped, j.failed,
                   j.created_at, s.title AS source_title, t.title AS target_title
            FROM jobs j
            LEFT JOIN sources s ON s.id = j.source_id
            LEFT JOIN targets t ON t.id = j.target_id
            ORDER BY j.id DESC LIMIT 200
            """
        ).fetchall()
        payload = tuple(
            {
                "id": int(row["id"]), "name": row["name"], "state": row["state"],
                "total": int(row["total"]), "success": int(row["success"]),
                "skipped": int(row["skipped"]), "failed": int(row["failed"]),
                "source": row["source_title"] or "", "target": row["target_title"] or "",
                "created_at": row["created_at"],
            }
            for row in rows
        )
        self.event_emitted.emit(JobsUpdatedEvent(jobs=payload))

    def _emit_logs(self, limit: int) -> None:
        rows = AuditRepository(self._connection).recent(max(1, min(limit, 1000)))
        payload = tuple(
            {
                "id": int(row["id"]), "event_type": row["event_type"],
                "entity_type": row["entity_type"] or "", "entity_id": row["entity_id"] or "",
                "details": json.loads(row["details_json"]), "created_at": row["created_at"],
            }
            for row in rows
        )
        self.event_emitted.emit(LogsUpdatedEvent(entries=payload))
