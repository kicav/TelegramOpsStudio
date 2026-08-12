from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import socks
from telethon import TelegramClient
from telethon.errors import (
    ChatAdminRequiredError, ChatWriteForbiddenError, FloodWaitError,
    PhoneCodeInvalidError, SessionPasswordNeededError, UserAlreadyParticipantError,
    UserChannelsTooMuchError, UserPrivacyRestrictedError,
)
from telethon.tl.functions.channels import InviteToChannelRequest, JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import InputUser, UserStatusOffline, UserStatusOnline, UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth

from . import credentials
from .db import Database


def _proxy_tuple(account) -> tuple | None:
    host = account["proxy_host"]
    if not host:
        return None
    typ = (account["proxy_type"] or "socks5").lower()
    proxy_kind = socks.SOCKS5 if typ == "socks5" else socks.HTTP
    return (proxy_kind, host, int(account["proxy_port"]), True,
            account["proxy_user"] or None, account["proxy_pass"] or None)


def _status_text(status) -> str:
    if isinstance(status, UserStatusOnline):
        return "online"
    if isinstance(status, UserStatusOffline):
        return status.was_online.astimezone(timezone.utc).isoformat() if status.was_online else "offline"
    if isinstance(status, UserStatusRecently):
        return "recently"
    if isinstance(status, UserStatusLastWeek):
        return "last_week"
    if isinstance(status, UserStatusLastMonth):
        return "last_month"
    return "unknown"


def _invite_hash(identifier: str) -> str | None:
    for marker in ("t.me/+", "t.me/joinchat/"):
        if marker in identifier:
            return identifier.split(marker, 1)[1].split("?", 1)[0].strip("/")
    return None


class TelegramAccountClient:
    def __init__(self, db: Database, account_id: int):
        self.db = db
        self.account = db.account(account_id)
        if not self.account:
            raise ValueError("Account not found")
        api_hash = credentials.get_api_hash(self.account["phone"])
        if not api_hash:
            raise RuntimeError("API hash is not available in OS credential store")
        self.client = TelegramClient(
            self.account["session_file"], int(self.account["api_id"]), api_hash,
            proxy=_proxy_tuple(self.account), sequential_updates=True,
        )

    async def __aenter__(self):
        await self.client.connect()
        if not await self.client.is_user_authorized():
            await self.client.disconnect()
            raise RuntimeError("Session is not authorized")
        return self.client

    async def __aexit__(self, *exc):
        await self.client.disconnect()


async def authorize_account(db: Database, phone: str, api_id: int, api_hash: str, session_file: str,
                            code_provider, password_provider) -> dict:
    client = TelegramClient(session_file, api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            sent = await client.send_code_request(phone)
            code = code_provider()
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
            except SessionPasswordNeededError:
                await client.sign_in(password=password_provider())
        me = await client.get_me()
        credentials.set_api_hash(phone, api_hash)
        account_id = db.add_account(
            phone, api_id, session_file,
            display_name=" ".join(x for x in [getattr(me, "first_name", ""), getattr(me, "last_name", "")] if x),
            username=getattr(me, "username", "") or "", status="Authorized",
        )
        return {"account_id": account_id, "phone": phone, "username": getattr(me, "username", "") or ""}
    finally:
        await client.disconnect()


async def permissions(client: TelegramClient, entity) -> dict:
    p = await client.get_permissions(entity, "me")
    is_creator = bool(getattr(p, "is_creator", False))
    is_admin = bool(getattr(p, "is_admin", False))
    can_invite = bool(getattr(p, "invite_users", False)) or is_creator
    return {"is_creator": is_creator, "is_admin": is_admin, "can_invite": can_invite,
            "managed": is_creator or is_admin}


async def resolve_or_join(client: TelegramClient, identifier: str, allow_join: bool = False):
    ih = _invite_hash(identifier)
    if ih:
        if not allow_join:
            raise PermissionError("Private invite requires explicit Join action")
        try:
            result = await client(ImportChatInviteRequest(ih))
            return result.chats[0]
        except UserAlreadyParticipantError:
            return await client.get_entity(identifier)
    entity = await client.get_entity(identifier)
    if allow_join:
        try:
            await client(JoinChannelRequest(entity))
        except UserAlreadyParticipantError:
            pass
    return entity


class ScannerService:
    def __init__(self, db: Database):
        self.db = db

    async def overview(self, account_id: int, identifier: str) -> dict:
        async with TelegramAccountClient(self.db, account_id) as client:
            entity = await client.get_entity(identifier)
            p = await permissions(client, entity)
            count = getattr(entity, "participants_count", 0) or 0
            title = getattr(entity, "title", identifier)
            self.db.upsert_group(account_id, getattr(entity, "id", None), title, identifier, p["managed"], count)
            return {"title": title, "participants": count, **p}

    async def scan_managed(self, account_id: int, identifier: str, limit: int = 5000,
                           filter_bots: bool = True, filter_deleted: bool = True) -> dict:
        async with TelegramAccountClient(self.db, account_id) as client:
            entity = await client.get_entity(identifier)
            p = await permissions(client, entity)
            if not p["managed"]:
                raise PermissionError("Detailed identity scan is limited to groups this account administers")
            rows = []
            async for user in client.iter_participants(entity, limit=limit):
                if filter_bots and bool(getattr(user, "bot", False)):
                    continue
                if filter_deleted and bool(getattr(user, "deleted", False)):
                    continue
                rows.append({
                    "user_id": int(user.id), "access_hash": getattr(user, "access_hash", None),
                    "username": getattr(user, "username", "") or "", "first_name": getattr(user, "first_name", "") or "",
                    "last_name": getattr(user, "last_name", "") or "", "phone": getattr(user, "phone", "") or "",
                    "is_bot": bool(getattr(user, "bot", False)), "is_deleted": bool(getattr(user, "deleted", False)),
                    "last_seen": _status_text(getattr(user, "status", None)),
                })
            title = getattr(entity, "title", identifier)
            self.db.save_members(rows, identifier, source_managed=True)
            self.db.upsert_group(account_id, getattr(entity, "id", None), title, identifier, True, len(rows))
            return {"title": title, "saved": len(rows), "rows": rows}


@dataclass
class JobResult:
    success: int = 0
    failed: int = 0
    skipped: int = 0
    stopped_reason: str = ""


class InviteService:
    """Consent-based invite queue.

    It intentionally does not rotate accounts after Telegram restrictions and stops on FloodWait.
    """
    def __init__(self, db: Database):
        self.db = db

    async def run(self, account_id: int, target: str, limit: int = 20, delay_min: float = 8,
                  delay_max: float = 15, dry_run: bool = False, progress=None) -> JobResult:
        candidates = list(self.db.opted_in_members(limit))
        job_id = self.db.create_job("Invite", account_id, target, len(candidates))
        result = JobResult()
        account = self.db.account(account_id)
        phone = account["phone"]
        async with TelegramAccountClient(self.db, account_id) as client:
            entity = await client.get_entity(target)
            p = await permissions(client, entity)
            if not p["managed"] or not p["can_invite"]:
                raise PermissionError("Target must be administered by this account with invite permission")
            for idx, m in enumerate(candidates, 1):
                if progress:
                    progress(idx, len(candidates), m["username"] or str(m["user_id"]))
                if dry_run:
                    result.skipped += 1
                    self.db.log(job_id, "Invite", phone, target, "DryRun", m["user_id"], m["username"])
                    continue
                if not m["access_hash"]:
                    result.skipped += 1
                    self.db.update_member_result(m["id"], "Skipped", "Missing access_hash")
                    self.db.log(job_id, "Invite", phone, target, "Skipped", m["user_id"], m["username"], "NO_ACCESS_HASH")
                    continue
                try:
                    await client(InviteToChannelRequest(entity, [InputUser(int(m["user_id"]), int(m["access_hash"]))]))
                    result.success += 1
                    self.db.update_member_result(m["id"], "Invited")
                    self.db.log(job_id, "Invite", phone, target, "Success", m["user_id"], m["username"])
                except UserAlreadyParticipantError:
                    result.skipped += 1
                    self.db.update_member_result(m["id"], "Skipped", "Already participant")
                    self.db.log(job_id, "Invite", phone, target, "Skipped", m["user_id"], m["username"], "ALREADY_PARTICIPANT")
                except (UserPrivacyRestrictedError, UserChannelsTooMuchError) as e:
                    result.failed += 1
                    code = type(e).__name__
                    self.db.update_member_result(m["id"], "Failed", code)
                    self.db.log(job_id, "Invite", phone, target, "Failed", m["user_id"], m["username"], code)
                except FloodWaitError as e:
                    result.stopped_reason = f"FloodWait {e.seconds}s"
                    self.db.log(job_id, "Invite", phone, target, "Stopped", m["user_id"], m["username"], "FLOOD_WAIT", str(e.seconds))
                    break
                except (ChatAdminRequiredError, ChatWriteForbiddenError) as e:
                    result.stopped_reason = type(e).__name__
                    break
                except Exception as e:
                    result.failed += 1
                    self.db.update_member_result(m["id"], "Failed", type(e).__name__)
                    self.db.log(job_id, "Invite", phone, target, "Failed", m["user_id"], m["username"], type(e).__name__, str(e)[:300])
                await asyncio.sleep(random.uniform(delay_min, delay_max))
        self.db.finish_job(job_id, result.success, result.failed, result.skipped, result.stopped_reason)
        return result


class MessengerService:
    def __init__(self, db: Database):
        self.db = db

    async def send_group(self, account_id: int, target: str, text: str) -> None:
        account = self.db.account(account_id)
        async with TelegramAccountClient(self.db, account_id) as client:
            entity = await client.get_entity(target)
            p = await permissions(client, entity)
            if not p["managed"]:
                raise PermissionError("Group messaging is limited to groups this account administers")
            await client.send_message(entity, text)
            self.db.log(None, "GroupMessage", account["phone"], target, "Success")

    async def send_opted_in(self, account_id: int, text: str, limit: int = 20,
                            delay_min: float = 8, delay_max: float = 15, progress=None) -> JobResult:
        members = list(self.db.opted_in_members(limit))
        account = self.db.account(account_id)
        job_id = self.db.create_job("DirectMessage", account_id, "opted_in", len(members))
        result = JobResult()
        async with TelegramAccountClient(self.db, account_id) as client:
            for idx, m in enumerate(members, 1):
                if progress:
                    progress(idx, len(members), m["username"] or str(m["user_id"]))
                try:
                    peer = InputUser(int(m["user_id"]), int(m["access_hash"])) if m["access_hash"] else (m["username"] or None)
                    if not peer:
                        raise ValueError("No resolvable peer")
                    await client.send_message(peer, text)
                    result.success += 1
                    self.db.update_member_result(m["id"], "Messaged")
                    self.db.log(job_id, "DirectMessage", account["phone"], "user", "Success", m["user_id"], m["username"])
                except FloodWaitError as e:
                    result.stopped_reason = f"FloodWait {e.seconds}s"
                    break
                except Exception as e:
                    result.failed += 1
                    self.db.log(job_id, "DirectMessage", account["phone"], "user", "Failed", m["user_id"], m["username"], type(e).__name__, str(e)[:300])
                await asyncio.sleep(random.uniform(delay_min, delay_max))
        self.db.finish_job(job_id, result.success, result.failed, result.skipped, result.stopped_reason)
        return result


class JoinService:
    def __init__(self, db: Database):
        self.db = db

    async def join(self, account_id: int, identifier: str) -> str:
        account = self.db.account(account_id)
        async with TelegramAccountClient(self.db, account_id) as client:
            entity = await resolve_or_join(client, identifier, allow_join=True)
            self.db.log(None, "Join", account["phone"], identifier, "Success")
            return getattr(entity, "title", identifier)

    async def leave(self, account_id: int, identifier: str) -> None:
        account = self.db.account(account_id)
        async with TelegramAccountClient(self.db, account_id) as client:
            entity = await client.get_entity(identifier)
            await client(LeaveChannelRequest(entity))
            self.db.log(None, "Leave", account["phone"], identifier, "Success")

class MessageArchiveService:
    def __init__(self, db: Database):
        self.db = db

    async def archive_managed(self, account_id: int, identifier: str, limit: int = 200) -> list[dict]:
        async with TelegramAccountClient(self.db, account_id) as client:
            entity = await client.get_entity(identifier)
            p = await permissions(client, entity)
            if not p["managed"]:
                raise PermissionError("Message archive is limited to groups this account administers")
            out = []
            async for msg in client.iter_messages(entity, limit=limit):
                out.append({
                    "message_id": msg.id,
                    "sender_id": getattr(msg, "sender_id", None),
                    "date": msg.date.isoformat() if msg.date else "",
                    "text": msg.message or "",
                    "reply_to_message_id": getattr(getattr(msg, "reply_to", None), "reply_to_msg_id", None),
                    "has_media": bool(msg.media),
                    "media_type": type(msg.media).__name__ if msg.media else "",
                })
            return out


class ScriptService:
    """Runs a scripted message sequence only in a group administered by the account."""
    def __init__(self, db: Database):
        self.db = db

    async def run_managed_sequence(self, account_id: int, target: str, steps: list[dict], repeat: int = 1,
                                   progress=None) -> JobResult:
        account = self.db.account(account_id)
        job_id = self.db.create_job("ManagedScript", account_id, target, len(steps) * repeat)
        result = JobResult()
        async with TelegramAccountClient(self.db, account_id) as client:
            entity = await client.get_entity(target)
            p = await permissions(client, entity)
            if not p["managed"]:
                raise PermissionError("Scripts are limited to groups this account administers")
            sent_ids: dict[int, int] = {}
            total = len(steps) * repeat
            current = 0
            for _ in range(repeat):
                sent_ids.clear()
                for idx, step in enumerate(steps):
                    current += 1
                    if progress:
                        progress(current, total, step.get("text", "")[:60])
                    delay = float(step.get("delay", 0) or 0)
                    reply_idx = step.get("reply_to_index")
                    reply_to = sent_ids.get(int(reply_idx)) if reply_idx not in (None, "") else None
                    try:
                        m = await client.send_message(entity, step.get("text", ""), reply_to=reply_to)
                        sent_ids[idx] = m.id
                        result.success += 1
                        self.db.log(job_id, "ManagedScript", account["phone"], target, "Success", detail=f"step={idx}")
                    except FloodWaitError as e:
                        result.stopped_reason = f"FloodWait {e.seconds}s"
                        break
                    except Exception as e:
                        result.failed += 1
                        self.db.log(job_id, "ManagedScript", account["phone"], target, "Failed", error_code=type(e).__name__, detail=str(e)[:300])
                    if delay > 0:
                        await asyncio.sleep(delay)
                if result.stopped_reason:
                    break
        self.db.finish_job(job_id, result.success, result.failed, result.skipped, result.stopped_reason)
        return result
