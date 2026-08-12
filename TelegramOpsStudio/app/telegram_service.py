from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from typing import Callable, Iterable

import socks
from telethon import TelegramClient, types, utils
from telethon.errors import (
    AuthKeyUnregisteredError,
    ChannelPrivateError,
    ChannelsTooMuchError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
    FloodWaitError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberBannedError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
    UserAlreadyParticipantError,
    UserBannedInChannelError,
    UserChannelsTooMuchError,
    UserPrivacyRestrictedError,
    UserNotParticipantError,
)
from telethon.tl.functions.channels import InviteToChannelRequest, JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import (
    AddChatUserRequest,
    CheckChatInviteRequest,
    DeleteChatUserRequest,
    ImportChatInviteRequest,
)
from telethon.tl.types import (
    InputUser,
    UserStatusLastMonth,
    UserStatusLastWeek,
    UserStatusOffline,
    UserStatusOnline,
    UserStatusRecently,
)

from . import credentials
from .db import Database

ProgressFn = Callable[[int, int, str], None] | None


class TwoFactorRequired(RuntimeError):
    """Raised after a correct login code when Telegram requires the 2FA password."""


def _status_text(status) -> str:
    if isinstance(status, UserStatusOnline):
        return "online"
    if isinstance(status, UserStatusOffline):
        if not status.was_online:
            return "offline"
        dt = status.was_online
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    if isinstance(status, UserStatusRecently):
        return "recently"
    if isinstance(status, UserStatusLastWeek):
        return "last_week"
    if isinstance(status, UserStatusLastMonth):
        return "last_month"
    return "unknown"


def invite_hash(identifier: str) -> str | None:
    value = identifier.strip()
    for marker in ("t.me/+", "telegram.me/+", "t.me/joinchat/", "telegram.me/joinchat/"):
        if marker in value:
            return value.split(marker, 1)[1].split("?", 1)[0].strip("/")
    return None


def _proxy_tuple(account) -> tuple | None:
    if not account or not account["proxy_id"] or not account["proxy_host"] or not account["proxy_enabled"]:
        return None
    proxy_type = (account["proxy_type"] or "socks5").lower()
    kinds = {"socks5": socks.SOCKS5, "socks4": socks.SOCKS4, "http": socks.HTTP}
    if proxy_type not in kinds:
        raise ValueError(f"Unsupported proxy type: {proxy_type}")
    password = credentials.get_proxy_password(int(account["proxy_id"])) or None
    return (
        kinds[proxy_type], account["proxy_host"], int(account["proxy_port"]), True,
        account["proxy_user"] or None, password,
    )


class TelegramAccountClient:
    def __init__(self, db: Database, account_id: int):
        self.db = db
        self.account = db.account(account_id)
        if not self.account:
            raise ValueError("Account not found")
        api_hash = credentials.get_api_hash(self.account["phone"])
        if not api_hash:
            raise RuntimeError("API hash is not available in the OS credential store")
        self.client = TelegramClient(
            self.account["session_file"],
            int(self.account["api_id"]),
            api_hash,
            proxy=_proxy_tuple(self.account),
            sequential_updates=True,
        )
        # Make server rate limits explicit to the caller instead of Telethon auto-sleeping.
        self.client.flood_sleep_threshold = 0

    async def __aenter__(self) -> TelegramClient:
        await self.client.connect()
        if not await self.client.is_user_authorized():
            await self.client.disconnect()
            raise RuntimeError("Session is not authorized")
        self.db.mark_account_used(int(self.account["id"]))
        return self.client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.client.disconnect()


async def request_login_code(phone: str, api_id: int, api_hash: str, session_file: str) -> str:
    client = TelegramClient(session_file, int(api_id), api_hash)
    client.flood_sleep_threshold = 0
    await client.connect()
    try:
        if await client.is_user_authorized():
            return "ALREADY_AUTHORIZED"
        sent = await client.send_code_request(phone)
        return sent.phone_code_hash
    finally:
        await client.disconnect()


async def _save_authorized_account(
    db: Database, client: TelegramClient, phone: str, api_id: int, api_hash: str, session_file: str,
) -> dict:
    me = await client.get_me()
    credentials.set_api_hash(phone, api_hash)
    display_name = " ".join(
        value for value in (getattr(me, "first_name", "") or "", getattr(me, "last_name", "") or "") if value
    )
    account_id = db.add_account(
        phone, int(api_id), session_file,
        display_name=display_name,
        username=getattr(me, "username", "") or "",
        status="Authorized",
    )
    return {"account_id": account_id, "phone": phone, "username": getattr(me, "username", "") or ""}


async def complete_login_code(
    db: Database, phone: str, api_id: int, api_hash: str, session_file: str,
    code: str, phone_code_hash: str,
) -> dict:
    client = TelegramClient(session_file, int(api_id), api_hash)
    client.flood_sleep_threshold = 0
    await client.connect()
    try:
        if not await client.is_user_authorized():
            try:
                await client.sign_in(phone=phone, code=code.strip(), phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError as exc:
                raise TwoFactorRequired("Telegram 2FA password is required") from exc
        return await _save_authorized_account(db, client, phone, api_id, api_hash, session_file)
    finally:
        await client.disconnect()


async def complete_login_password(
    db: Database, phone: str, api_id: int, api_hash: str, session_file: str, password: str,
) -> dict:
    client = TelegramClient(session_file, int(api_id), api_hash)
    client.flood_sleep_threshold = 0
    await client.connect()
    try:
        if not await client.is_user_authorized():
            await client.sign_in(password=password)
        return await _save_authorized_account(db, client, phone, api_id, api_hash, session_file)
    finally:
        await client.disconnect()


async def permissions(client: TelegramClient, entity) -> dict:
    try:
        current = await client.get_me()
        p = await client.get_permissions(entity, current)
    except (ChatAdminRequiredError, ChannelPrivateError, UserNotParticipantError):
        return {"is_creator": False, "is_admin": False, "can_invite": False, "managed": False}
    is_creator = bool(getattr(p, "is_creator", False) or getattr(p, "creator", False))
    is_admin = bool(getattr(p, "is_admin", False) or getattr(p, "admin_rights", None))
    rights = getattr(p, "admin_rights", None)
    can_invite = (
        bool(getattr(p, "invite_users", False))
        or bool(getattr(rights, "invite_users", False))
        or is_creator
        or (isinstance(entity, types.Chat) and is_admin)
    )
    return {
        "is_creator": is_creator,
        "is_admin": is_admin,
        "can_invite": can_invite,
        "managed": is_creator or is_admin,
    }


async def resolve_or_join(client: TelegramClient, identifier: str, allow_join: bool = False):
    identifier = identifier.strip()
    ih = invite_hash(identifier)
    if ih:
        if not allow_join:
            checked = await client(CheckChatInviteRequest(ih))
            chat = getattr(checked, "chat", None)
            if chat is None:
                raise PermissionError("Private invite is not joined; use Join / Leave first")
            return chat
        try:
            result = await client(ImportChatInviteRequest(ih))
            if result.chats:
                return result.chats[0]
        except UserAlreadyParticipantError:
            checked = await client(CheckChatInviteRequest(ih))
            chat = getattr(checked, "chat", None)
            if chat is not None:
                return chat
            raise
    entity = await client.get_entity(identifier)
    if allow_join and isinstance(entity, types.Channel):
        try:
            await client(JoinChannelRequest(entity))
        except UserAlreadyParticipantError:
            pass
    return entity


class ScannerService:
    def __init__(self, db: Database):
        self.db = db

    async def list_joined_groups(self, account_id: int, limit: int = 500) -> list[dict]:
        out: list[dict] = []
        async with TelegramAccountClient(self.db, account_id) as client:
            async for dialog in client.iter_dialogs(limit=limit):
                if not (dialog.is_group or dialog.is_channel):
                    continue
                entity = dialog.entity
                username = getattr(entity, "username", None)
                identifier = f"@{username}" if username else str(getattr(entity, "id", ""))
                out.append({
                    "peer_id": getattr(entity, "id", None),
                    "title": dialog.name or identifier,
                    "identifier": identifier,
                    "participants": int(getattr(entity, "participants_count", 0) or 0),
                })
        return out

    async def overview(self, account_id: int, identifier: str) -> dict:
        if not identifier.strip():
            raise ValueError("Group identifier is required")
        async with TelegramAccountClient(self.db, account_id) as client:
            entity = await resolve_or_join(client, identifier, allow_join=False)
            p = await permissions(client, entity)
            count = int(getattr(entity, "participants_count", 0) or 0)
            title = getattr(entity, "title", identifier)
            self.db.upsert_group(account_id, getattr(entity, "id", None), title, identifier, p["managed"], count)
            return {"title": title, "participants": count, **p}

    async def scan_managed(
        self, account_id: int, identifier: str, limit: int = 5000,
        filter_bots: bool = True, filter_deleted: bool = True, progress: ProgressFn = None,
    ) -> dict:
        if not identifier.strip():
            raise ValueError("Group identifier is required")
        if limit <= 0:
            raise ValueError("Scan limit must be positive")
        async with TelegramAccountClient(self.db, account_id) as client:
            entity = await resolve_or_join(client, identifier, allow_join=False)
            p = await permissions(client, entity)
            if not p["managed"]:
                raise PermissionError("Detailed identity scan is limited to groups this account administers")
            rows: list[dict] = []
            async for user in client.iter_participants(entity, limit=limit):
                if filter_bots and bool(getattr(user, "bot", False)):
                    continue
                if filter_deleted and bool(getattr(user, "deleted", False)):
                    continue
                rows.append({
                    "user_id": int(user.id),
                    "access_hash": getattr(user, "access_hash", None),
                    "username": getattr(user, "username", "") or "",
                    "first_name": getattr(user, "first_name", "") or "",
                    "last_name": getattr(user, "last_name", "") or "",
                    "phone": getattr(user, "phone", "") or "",
                    "is_bot": bool(getattr(user, "bot", False)),
                    "is_deleted": bool(getattr(user, "deleted", False)),
                    "has_photo": getattr(user, "photo", None) is not None,
                    "last_seen": _status_text(getattr(user, "status", None)),
                })
                if progress and len(rows) % 25 == 0:
                    progress(len(rows), limit, rows[-1]["username"] or str(rows[-1]["user_id"]))
            title = getattr(entity, "title", identifier)
            self.db.save_members(rows, identifier, source_managed=True)
            participant_count = int(getattr(entity, "participants_count", 0) or len(rows))
            self.db.upsert_group(account_id, getattr(entity, "id", None), title, identifier, True, participant_count)
            return {"title": title, "saved": len(rows), "rows": rows}


@dataclass
class JobResult:
    success: int = 0
    failed: int = 0
    skipped: int = 0
    stopped_reason: str = ""


class InviteService:
    """Consent-based, sequential invite queue.

    Telegram restrictions stop the current job. This service deliberately does not rotate
    accounts or proxies in response to FloodWait/anti-spam restrictions.
    """

    def __init__(self, db: Database):
        self.db = db

    async def run(
        self, account_id: int, target: str, limit: int = 20, delay_min: float = 8,
        delay_max: float = 15, dry_run: bool = True, progress: ProgressFn = None,
        source: str | None = None, offset: int = 0,
    ) -> JobResult:
        if not target.strip():
            raise ValueError("Target group is required")
        if int(limit) <= 0:
            raise ValueError("Invite limit must be positive")
        if int(offset) < 0:
            raise ValueError("Invite offset cannot be negative")
        if delay_min < 0 or delay_max < delay_min:
            raise ValueError("Invalid invite delay range")
        daily_cap = max(1, int(self.db.get_setting("daily_invite_cap", "20")))
        used_today = self.db.account_daily_invite_count(account_id)
        remaining_today = max(0, daily_cap - used_today)
        effective_limit = int(limit) if dry_run else min(int(limit), remaining_today)
        if not dry_run and effective_limit <= 0:
            raise RuntimeError(f"Daily invite cap ({daily_cap}) has already been reached for this account")

        candidates = list(self.db.opted_in_members(max(0, effective_limit), source=source, offset=offset))
        job_id = self.db.create_job("Invite", account_id, target, len(candidates))
        result = JobResult()
        account = self.db.account(account_id)
        if not account:
            self.db.finish_job(job_id, 0, 0, 0, "Account not found", "Failed")
            raise ValueError("Account not found")
        phone = account["phone"]
        try:
            async with TelegramAccountClient(self.db, account_id) as client:
                entity = await resolve_or_join(client, target, allow_join=False)
                p = await permissions(client, entity)
                if not p["managed"] or not p["can_invite"]:
                    raise PermissionError("Target must be administered by this account with invite permission")
                for idx, member in enumerate(candidates, 1):
                    label = member["username"] or str(member["user_id"])
                    if progress:
                        progress(idx, len(candidates), label)
                    if dry_run:
                        result.skipped += 1
                        self.db.log(job_id, "Invite", phone, target, "DryRun", member["user_id"], member["username"])
                        continue
                    if not member["access_hash"]:
                        result.skipped += 1
                        self.db.update_member_result(member["id"], "Skipped", "Missing access_hash")
                        self.db.log(job_id, "Invite", phone, target, "Skipped", member["user_id"], member["username"], "NO_ACCESS_HASH")
                        continue
                    peer = InputUser(int(member["user_id"]), int(member["access_hash"]))
                    try:
                        if isinstance(entity, types.Chat):
                            await client(AddChatUserRequest(entity.id, peer, fwd_limit=0))
                        else:
                            await client(InviteToChannelRequest(entity, [peer]))
                        result.success += 1
                        self.db.increment_account_counter(account_id, invites=1)
                        self.db.update_member_result(member["id"], "Invited")
                        self.db.log(job_id, "Invite", phone, target, "Success", member["user_id"], member["username"])
                    except UserAlreadyParticipantError:
                        result.skipped += 1
                        self.db.update_member_result(member["id"], "Skipped", "Already participant")
                        self.db.log(job_id, "Invite", phone, target, "Skipped", member["user_id"], member["username"], "ALREADY_PARTICIPANT")
                    except (UserPrivacyRestrictedError, UserChannelsTooMuchError) as exc:
                        result.failed += 1
                        code = type(exc).__name__
                        self.db.update_member_result(member["id"], "Failed", code)
                        self.db.log(job_id, "Invite", phone, target, "Failed", member["user_id"], member["username"], code)
                    except FloodWaitError as exc:
                        result.stopped_reason = f"FloodWait {exc.seconds}s"
                        self.db.log(job_id, "Invite", phone, target, "Stopped", member["user_id"], member["username"], "FLOOD_WAIT", str(exc.seconds))
                        break
                    except (ChatAdminRequiredError, ChatWriteForbiddenError) as exc:
                        result.stopped_reason = type(exc).__name__
                        self.db.log(job_id, "Invite", phone, target, "Stopped", member["user_id"], member["username"], type(exc).__name__)
                        break
                    except Exception as exc:
                        result.failed += 1
                        code = type(exc).__name__
                        self.db.update_member_result(member["id"], "Failed", code)
                        self.db.log(job_id, "Invite", phone, target, "Failed", member["user_id"], member["username"], code, str(exc)[:300])
                    if idx < len(candidates):
                        await asyncio.sleep(random.uniform(delay_min, delay_max))
            self.db.finish_job(job_id, result.success, result.failed, result.skipped, result.stopped_reason)
            return result
        except Exception as exc:
            self.db.finish_job(job_id, result.success, result.failed, result.skipped, str(exc), "Failed")
            raise


class MessengerService:
    def __init__(self, db: Database):
        self.db = db

    async def send_group(self, account_id: int, target: str, text: str, file_path: str = "") -> None:
        if not text.strip() and not file_path:
            raise ValueError("Message or file is required")
        account = self.db.account(account_id)
        if not account:
            raise ValueError("Account not found")
        async with TelegramAccountClient(self.db, account_id) as client:
            entity = await resolve_or_join(client, target, allow_join=False)
            p = await permissions(client, entity)
            if not p["managed"]:
                raise PermissionError("Group messaging is limited to groups this account administers")
            await client.send_message(entity, text or None, file=file_path or None)
            self.db.increment_account_counter(account_id, messages=1)
            self.db.log(None, "GroupMessage", account["phone"], target, "Success")

    async def send_managed_groups(
        self, account_id: int, targets: Iterable[str], text: str, file_path: str = "",
        delay: float = 2.0, progress: ProgressFn = None,
    ) -> JobResult:
        if not text.strip() and not file_path:
            raise ValueError("Message or file is required")
        if delay < 0:
            raise ValueError("Delay cannot be negative")
        clean_targets = [item.strip() for item in targets if item.strip()]
        if not clean_targets:
            raise ValueError("At least one managed group is required")
        job_id = self.db.create_job("ManagedBroadcast", account_id, "multiple_managed_groups", len(clean_targets))
        result = JobResult()
        account = self.db.account(account_id)
        if not account:
            self.db.finish_job(job_id, 0, 0, 0, "Account not found", "Failed")
            raise ValueError("Account not found")
        try:
            async with TelegramAccountClient(self.db, account_id) as client:
                for idx, target in enumerate(clean_targets, 1):
                    if progress:
                        progress(idx, len(clean_targets), target)
                    try:
                        entity = await resolve_or_join(client, target, allow_join=False)
                        p = await permissions(client, entity)
                        if not p["managed"]:
                            raise PermissionError("Not administered by selected account")
                        await client.send_message(entity, text or None, file=file_path or None)
                        result.success += 1
                        self.db.increment_account_counter(account_id, messages=1)
                        self.db.log(job_id, "ManagedBroadcast", account["phone"], target, "Success")
                    except FloodWaitError as exc:
                        result.stopped_reason = f"FloodWait {exc.seconds}s"
                        self.db.log(job_id, "ManagedBroadcast", account["phone"], target, "Stopped", error_code="FLOOD_WAIT", detail=str(exc.seconds))
                        break
                    except Exception as exc:
                        result.failed += 1
                        self.db.log(job_id, "ManagedBroadcast", account["phone"], target, "Failed", error_code=type(exc).__name__, detail=str(exc)[:300])
                    if idx < len(clean_targets) and delay > 0:
                        await asyncio.sleep(delay)
            self.db.finish_job(job_id, result.success, result.failed, result.skipped, result.stopped_reason)
            return result
        except Exception as exc:
            self.db.finish_job(job_id, result.success, result.failed, result.skipped, str(exc), "Failed")
            raise

    async def send_opted_in(
        self, account_id: int, text: str, limit: int = 20, delay_min: float = 8,
        delay_max: float = 15, progress: ProgressFn = None, source: str | None = None,
        offset: int = 0, file_path: str = "",
    ) -> JobResult:
        if not text.strip() and not file_path:
            raise ValueError("Message or file is required")
        if int(limit) <= 0:
            raise ValueError("Message limit must be positive")
        if int(offset) < 0:
            raise ValueError("Message offset cannot be negative")
        if delay_min < 0 or delay_max < delay_min:
            raise ValueError("Invalid message delay range")
        members = list(self.db.opted_in_members(limit, source=source, offset=offset))
        account = self.db.account(account_id)
        if not account:
            raise ValueError("Account not found")
        job_id = self.db.create_job("DirectMessage", account_id, source or "opted_in", len(members))
        result = JobResult()
        try:
            async with TelegramAccountClient(self.db, account_id) as client:
                for idx, member in enumerate(members, 1):
                    if progress:
                        progress(idx, len(members), member["username"] or str(member["user_id"]))
                    try:
                        peer = InputUser(int(member["user_id"]), int(member["access_hash"])) if member["access_hash"] else (member["username"] or None)
                        if not peer:
                            raise ValueError("No resolvable peer")
                        await client.send_message(peer, text or None, file=file_path or None)
                        result.success += 1
                        self.db.increment_account_counter(account_id, messages=1)
                        self.db.update_member_result(member["id"], "Messaged")
                        self.db.log(job_id, "DirectMessage", account["phone"], "user", "Success", member["user_id"], member["username"])
                    except FloodWaitError as exc:
                        result.stopped_reason = f"FloodWait {exc.seconds}s"
                        self.db.log(job_id, "DirectMessage", account["phone"], "user", "Stopped", member["user_id"], member["username"], "FLOOD_WAIT", str(exc.seconds))
                        break
                    except Exception as exc:
                        result.failed += 1
                        code = type(exc).__name__
                        self.db.update_member_result(member["id"], "Failed", code)
                        self.db.log(job_id, "DirectMessage", account["phone"], "user", "Failed", member["user_id"], member["username"], code, str(exc)[:300])
                    if idx < len(members):
                        await asyncio.sleep(random.uniform(delay_min, delay_max))
            self.db.finish_job(job_id, result.success, result.failed, result.skipped, result.stopped_reason)
            return result
        except Exception as exc:
            self.db.finish_job(job_id, result.success, result.failed, result.skipped, str(exc), "Failed")
            raise


class JoinService:
    def __init__(self, db: Database):
        self.db = db

    async def join(self, account_id: int, identifier: str) -> str:
        account = self.db.account(account_id)
        if not account:
            raise ValueError("Account not found")
        async with TelegramAccountClient(self.db, account_id) as client:
            entity = await resolve_or_join(client, identifier, allow_join=True)
            self.db.log(None, "Join", account["phone"], identifier, "Success")
            return getattr(entity, "title", identifier)

    async def leave(self, account_id: int, identifier: str) -> None:
        account = self.db.account(account_id)
        if not account:
            raise ValueError("Account not found")
        async with TelegramAccountClient(self.db, account_id) as client:
            entity = await resolve_or_join(client, identifier, allow_join=False)
            if isinstance(entity, types.Chat):
                me = await client.get_me()
                if me is None:
                    raise RuntimeError("Could not resolve the authorized account")
                await client(DeleteChatUserRequest(entity.id, utils.get_input_user(me)))
            else:
                await client(LeaveChannelRequest(entity))
            self.db.log(None, "Leave", account["phone"], identifier, "Success")


class MessageArchiveService:
    def __init__(self, db: Database):
        self.db = db

    async def archive_managed(
        self, account_id: int, identifier: str, limit: int = 200,
        download_media: bool = False, media_dir: str = "", progress: ProgressFn = None,
    ) -> list[dict]:
        if download_media and not media_dir:
            raise ValueError("Media folder is required when download_media is enabled")
        target_dir = Path(media_dir) if media_dir else None
        if target_dir:
            target_dir.mkdir(parents=True, exist_ok=True)
        async with TelegramAccountClient(self.db, account_id) as client:
            entity = await resolve_or_join(client, identifier, allow_join=False)
            p = await permissions(client, entity)
            if not p["managed"]:
                raise PermissionError("Message archive is limited to groups this account administers")
            out: list[dict] = []
            async for msg in client.iter_messages(entity, limit=limit):
                saved_media = ""
                if download_media and msg.media:
                    try:
                        saved_media = str(await client.download_media(msg, file=str(target_dir)))
                    except Exception:
                        saved_media = ""
                out.append({
                    "message_id": msg.id,
                    "sender_id": getattr(msg, "sender_id", None),
                    "date": msg.date.isoformat() if msg.date else "",
                    "text": msg.message or "",
                    "reply_to_message_id": getattr(getattr(msg, "reply_to", None), "reply_to_msg_id", None),
                    "has_media": bool(msg.media),
                    "media_type": type(msg.media).__name__ if msg.media else "",
                    "saved_media": saved_media,
                })
                if progress and len(out) % 25 == 0:
                    progress(len(out), limit, str(msg.id))
            return out


class ScriptService:
    """Run message scripts only in groups administered by the selected account."""

    def __init__(self, db: Database):
        self.db = db

    async def run_managed_sequence(
        self, account_id: int, target: str, steps: list[dict], repeat: int = 1,
        progress: ProgressFn = None,
    ) -> JobResult:
        if not steps:
            raise ValueError("Script is empty")
        for idx, step in enumerate(steps):
            delay = float(step.get("delay", 0) or 0)
            if delay < 0:
                raise ValueError(f"Script step {idx}: delay cannot be negative")
            reply_idx = step.get("reply_to_index")
            if reply_idx not in (None, ""):
                reply_idx = int(reply_idx)
                if reply_idx < 0 or reply_idx >= idx:
                    raise ValueError(f"Script step {idx}: reply_to_index must reference an earlier step")
        account = self.db.account(account_id)
        if not account:
            raise ValueError("Account not found")
        job_id = self.db.create_job("ManagedScript", account_id, target, len(steps) * max(1, repeat))
        result = JobResult()
        try:
            async with TelegramAccountClient(self.db, account_id) as client:
                entity = await resolve_or_join(client, target, allow_join=False)
                p = await permissions(client, entity)
                if not p["managed"]:
                    raise PermissionError("Scripts are limited to groups this account administers")
                total = len(steps) * max(1, repeat)
                current = 0
                for _ in range(max(1, repeat)):
                    sent_ids: dict[int, int] = {}
                    for idx, step in enumerate(steps):
                        current += 1
                        text = str(step.get("text", ""))
                        file_path = str(step.get("file", "") or "")
                        if not text.strip() and not file_path:
                            result.skipped += 1
                            continue
                        if progress:
                            progress(current, total, text[:60] or Path(file_path).name)
                        delay = max(0.0, float(step.get("delay", 0) or 0))
                        reply_idx = step.get("reply_to_index")
                        reply_to = sent_ids.get(int(reply_idx)) if reply_idx not in (None, "") else None
                        try:
                            message = await client.send_message(
                                entity, text or None, file=file_path or None, reply_to=reply_to,
                            )
                            sent_ids[idx] = message.id
                            result.success += 1
                            self.db.increment_account_counter(account_id, messages=1)
                            self.db.log(job_id, "ManagedScript", account["phone"], target, "Success", detail=f"step={idx}")
                        except FloodWaitError as exc:
                            result.stopped_reason = f"FloodWait {exc.seconds}s"
                            self.db.log(job_id, "ManagedScript", account["phone"], target, "Stopped", error_code="FLOOD_WAIT", detail=str(exc.seconds))
                            break
                        except Exception as exc:
                            result.failed += 1
                            self.db.log(job_id, "ManagedScript", account["phone"], target, "Failed", error_code=type(exc).__name__, detail=str(exc)[:300])
                        if delay > 0:
                            await asyncio.sleep(delay)
                    if result.stopped_reason:
                        break
            self.db.finish_job(job_id, result.success, result.failed, result.skipped, result.stopped_reason)
            return result
        except Exception as exc:
            self.db.finish_job(job_id, result.success, result.failed, result.skipped, str(exc), "Failed")
            raise
