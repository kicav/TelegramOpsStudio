from __future__ import annotations

import csv
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .config import DB_PATH, DEFAULTS, ensure_dirs

SCHEMA_VERSION = 2

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL UNIQUE,
    api_id INTEGER NOT NULL,
    session_file TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    username TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Unknown',
    proxy_id INTEGER,
    invite_success_total INTEGER NOT NULL DEFAULT 0,
    message_success_total INTEGER NOT NULL DEFAULT 0,
    daily_invite_count INTEGER NOT NULL DEFAULT 0,
    daily_invite_date TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TEXT,
    last_used_at TEXT,
    FOREIGN KEY(proxy_id) REFERENCES proxies(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS proxies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proxy_type TEXT NOT NULL DEFAULT 'socks5'
        CHECK(proxy_type IN ('socks5','socks4','http')),
    host TEXT NOT NULL,
    port INTEGER NOT NULL CHECK(port BETWEEN 1 AND 65535),
    username TEXT DEFAULT '',
    label TEXT DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    UNIQUE(proxy_type, host, port, username)
);

CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    peer_id INTEGER,
    title TEXT NOT NULL,
    identifier TEXT NOT NULL,
    is_managed INTEGER NOT NULL DEFAULT 0,
    participant_count INTEGER DEFAULT 0,
    scanned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, identifier),
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    access_hash INTEGER,
    username TEXT DEFAULT '',
    first_name TEXT DEFAULT '',
    last_name TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    is_bot INTEGER NOT NULL DEFAULT 0,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    has_photo INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT DEFAULT '',
    source_group TEXT DEFAULT '',
    source_managed INTEGER NOT NULL DEFAULT 0,
    consent_status TEXT NOT NULL DEFAULT 'unknown'
        CHECK(consent_status IN ('unknown','opted_in','opted_out')),
    consent_note TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Pending'
        CHECK(status IN ('Pending','Invited','Messaged','Failed','Skipped')),
    last_error TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, source_group)
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    account_id INTEGER,
    target TEXT DEFAULT '',
    state TEXT NOT NULL DEFAULT 'Queued'
        CHECK(state IN ('Queued','Running','Finished','Failed','Cancelled')),
    total INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    action_type TEXT NOT NULL,
    account_phone TEXT DEFAULT '',
    target TEXT DEFAULT '',
    user_id INTEGER,
    username TEXT DEFAULT '',
    outcome TEXT NOT NULL,
    error_code TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class Database:
    def __init__(self, path: Path | str = DB_PATH):
        ensure_dirs()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self.path = str(p)
        with self.connect() as con:
            # proxies must exist before accounts because accounts references it.
            con.executescript(SCHEMA)
            self._migrate(con)
            for key, value in DEFAULTS.items():
                con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, value))

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def _columns(con: sqlite3.Connection, table: str) -> set[str]:
        return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}

    def _migrate(self, con: sqlite3.Connection) -> None:
        # Compatibility with early 0.1 databases.
        account_cols = self._columns(con, "accounts")
        additions = {
            "proxy_id": "INTEGER",
            "invite_success_total": "INTEGER NOT NULL DEFAULT 0",
            "message_success_total": "INTEGER NOT NULL DEFAULT 0",
            "daily_invite_count": "INTEGER NOT NULL DEFAULT 0",
            "daily_invite_date": "TEXT DEFAULT ''",
            "last_used_at": "TEXT",
        }
        for name, spec in additions.items():
            if name not in account_cols:
                con.execute(f"ALTER TABLE accounts ADD COLUMN {name} {spec}")

        member_cols = self._columns(con, "members")
        if "has_photo" not in member_cols:
            con.execute("ALTER TABLE members ADD COLUMN has_photo INTEGER NOT NULL DEFAULT 0")

        con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    # ---------- settings ----------
    def get_setting(self, key: str, default: str = "") -> str:
        with self.connect() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return str(row[0]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as con:
            con.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )

    # ---------- proxies ----------
    def add_proxy(self, proxy_type: str, host: str, port: int, username: str = "", label: str = "") -> int:
        proxy_type = proxy_type.strip().lower()
        host = host.strip()
        port = int(port)
        if proxy_type not in {"socks5", "socks4", "http"}:
            raise ValueError("proxy_type must be socks5, socks4 or http")
        if not host:
            raise ValueError("Proxy host is required")
        if not 1 <= port <= 65535:
            raise ValueError("Proxy port must be between 1 and 65535")
        with self.connect() as con:
            con.execute(
                """INSERT INTO proxies(proxy_type,host,port,username,label) VALUES(?,?,?,?,?)
                ON CONFLICT(proxy_type,host,port,username) DO UPDATE SET label=excluded.label,enabled=1""",
                (proxy_type, host, port, username.strip(), label.strip()),
            )
            row = con.execute(
                "SELECT id FROM proxies WHERE proxy_type=? AND host=? AND port=? AND username=?",
                (proxy_type, host, port, username.strip()),
            ).fetchone()
            return int(row[0])

    def proxies(self, enabled_only: bool = False):
        sql = "SELECT * FROM proxies"
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY id"
        with self.connect() as con:
            return con.execute(sql).fetchall()

    def proxy(self, proxy_id: int):
        with self.connect() as con:
            return con.execute("SELECT * FROM proxies WHERE id=?", (proxy_id,)).fetchone()

    def delete_proxy(self, proxy_id: int) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM proxies WHERE id=?", (proxy_id,))

    def set_proxy_enabled(self, proxy_id: int, enabled: bool) -> None:
        with self.connect() as con:
            con.execute("UPDATE proxies SET enabled=? WHERE id=?", (int(enabled), proxy_id))

    def assign_proxy(self, account_id: int, proxy_id: int | None) -> None:
        with self.connect() as con:
            if proxy_id is not None:
                row = con.execute("SELECT id FROM proxies WHERE id=? AND enabled=1", (proxy_id,)).fetchone()
                if not row:
                    raise ValueError("Proxy not found or disabled")
            con.execute("UPDATE accounts SET proxy_id=? WHERE id=?", (proxy_id, account_id))

    # ---------- accounts ----------
    def add_account(self, phone: str, api_id: int, session_file: str, **meta) -> int:
        with self.connect() as con:
            con.execute(
                """INSERT INTO accounts(phone,api_id,session_file,display_name,username,status)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(phone) DO UPDATE SET
                   api_id=excluded.api_id, session_file=excluded.session_file,
                   display_name=excluded.display_name, username=excluded.username,
                   status=excluded.status, last_checked_at=CURRENT_TIMESTAMP""",
                (
                    phone.strip(), int(api_id), session_file,
                    meta.get("display_name", ""), meta.get("username", ""), meta.get("status", "Authorized"),
                ),
            )
            return int(con.execute("SELECT id FROM accounts WHERE phone=?", (phone.strip(),)).fetchone()[0])

    def delete_account(self, account_id: int) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM accounts WHERE id=?", (account_id,))

    def accounts(self):
        with self.connect() as con:
            return con.execute(
                """SELECT a.*, p.proxy_type, p.host AS proxy_host, p.port AS proxy_port,
                          p.username AS proxy_user, p.label AS proxy_label, p.enabled AS proxy_enabled
                   FROM accounts a LEFT JOIN proxies p ON p.id=a.proxy_id ORDER BY a.id"""
            ).fetchall()

    def account(self, account_id: int):
        with self.connect() as con:
            return con.execute(
                """SELECT a.*, p.proxy_type, p.host AS proxy_host, p.port AS proxy_port,
                          p.username AS proxy_user, p.label AS proxy_label, p.enabled AS proxy_enabled
                   FROM accounts a LEFT JOIN proxies p ON p.id=a.proxy_id WHERE a.id=?""",
                (account_id,),
            ).fetchone()

    def mark_account_used(self, account_id: int) -> None:
        with self.connect() as con:
            con.execute("UPDATE accounts SET last_used_at=CURRENT_TIMESTAMP WHERE id=?", (account_id,))

    def account_daily_invite_count(self, account_id: int) -> int:
        today = _utc_date()
        with self.connect() as con:
            row = con.execute("SELECT daily_invite_date,daily_invite_count FROM accounts WHERE id=?", (account_id,)).fetchone()
            if not row:
                raise ValueError("Account not found")
            if row["daily_invite_date"] != today:
                con.execute(
                    "UPDATE accounts SET daily_invite_date=?,daily_invite_count=0 WHERE id=?",
                    (today, account_id),
                )
                return 0
            return int(row["daily_invite_count"] or 0)

    def increment_account_counter(self, account_id: int, *, invites: int = 0, messages: int = 0) -> None:
        today = _utc_date()
        with self.connect() as con:
            row = con.execute("SELECT daily_invite_date FROM accounts WHERE id=?", (account_id,)).fetchone()
            if not row:
                raise ValueError("Account not found")
            if row["daily_invite_date"] != today:
                con.execute(
                    "UPDATE accounts SET daily_invite_date=?,daily_invite_count=0 WHERE id=?",
                    (today, account_id),
                )
            con.execute(
                """UPDATE accounts SET invite_success_total=invite_success_total+?,
                   message_success_total=message_success_total+?, daily_invite_count=daily_invite_count+?,
                   last_used_at=CURRENT_TIMESTAMP WHERE id=?""",
                (int(invites), int(messages), int(invites), account_id),
            )

    # ---------- groups ----------
    def upsert_group(
        self, account_id: int, peer_id: int | None, title: str, identifier: str,
        is_managed: bool, participant_count: int | None,
    ) -> None:
        with self.connect() as con:
            con.execute(
                """INSERT INTO groups(account_id,peer_id,title,identifier,is_managed,participant_count,scanned_at)
                VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(account_id,identifier) DO UPDATE SET
                peer_id=excluded.peer_id,title=excluded.title,is_managed=excluded.is_managed,
                participant_count=excluded.participant_count,scanned_at=CURRENT_TIMESTAMP""",
                (account_id, peer_id, title, identifier, int(is_managed), int(participant_count or 0)),
            )

    def groups(self, account_id: int | None = None, managed_only: bool = False):
        sql = "SELECT * FROM groups WHERE 1=1"
        args: list[object] = []
        if account_id is not None:
            sql += " AND account_id=?"
            args.append(account_id)
        if managed_only:
            sql += " AND is_managed=1"
        sql += " ORDER BY title COLLATE NOCASE"
        with self.connect() as con:
            return con.execute(sql, args).fetchall()

    # ---------- members ----------
    def save_members(self, rows: Iterable[dict], source_group: str, source_managed: bool = True) -> int:
        count = 0
        with self.connect() as con:
            for member in rows:
                user_id = int(member["user_id"])
                consent = member.get("consent_status", "unknown")
                if consent not in {"unknown", "opted_in", "opted_out"}:
                    consent = "unknown"
                con.execute(
                    """INSERT INTO members(user_id,access_hash,username,first_name,last_name,phone,
                    is_bot,is_deleted,has_photo,last_seen,source_group,source_managed,consent_status,consent_note)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(user_id,source_group) DO UPDATE SET
                    access_hash=excluded.access_hash, username=excluded.username, first_name=excluded.first_name,
                    last_name=excluded.last_name, phone=excluded.phone, is_bot=excluded.is_bot,
                    is_deleted=excluded.is_deleted,has_photo=excluded.has_photo,last_seen=excluded.last_seen,
                    source_managed=excluded.source_managed,updated_at=CURRENT_TIMESTAMP""",
                    (
                        user_id, member.get("access_hash"), member.get("username", "") or "",
                        member.get("first_name", "") or "", member.get("last_name", "") or "",
                        member.get("phone", "") or "", int(bool(member.get("is_bot"))),
                        int(bool(member.get("is_deleted"))), int(bool(member.get("has_photo"))),
                        member.get("last_seen", "") or "", source_group, int(source_managed), consent,
                        member.get("consent_note", "") or "",
                    ),
                )
                count += 1
        return count

    def member_rows(
        self, *, bots: bool = True, deleted: bool = True, consent: str | None = None,
        source: str | None = None, username_contains: str = "", photo_filter: str = "all",
        active_within_days: int | None = None, offset: int = 0, limit: int | None = None,
    ):
        sql = "SELECT * FROM members WHERE 1=1"
        args: list[object] = []
        if not bots:
            sql += " AND is_bot=0"
        if not deleted:
            sql += " AND is_deleted=0"
        if consent:
            sql += " AND consent_status=?"
            args.append(consent)
        if source:
            sql += " AND source_group=?"
            args.append(source)
        if username_contains:
            sql += " AND username LIKE ?"
            args.append(f"%{username_contains.strip().lstrip('@')}%")
        if photo_filter == "has_photo":
            sql += " AND has_photo=1"
        elif photo_filter == "no_photo":
            sql += " AND has_photo=0"
        if active_within_days is not None:
            # ISO timestamps are lexicographically sortable. Category strings such as 'recently'
            # are intentionally excluded from exact day filtering.
            cutoff = datetime.now(timezone.utc).timestamp() - int(active_within_days) * 86400
            cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
            sql += " AND last_seen GLOB '????-??-??T*' AND last_seen>=?"
            args.append(cutoff_iso)
        sql += " ORDER BY id"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            args.extend([int(limit), max(0, int(offset))])
        with self.connect() as con:
            return con.execute(sql, args).fetchall()

    def member_sources(self) -> list[str]:
        with self.connect() as con:
            return [row[0] for row in con.execute("SELECT DISTINCT source_group FROM members ORDER BY source_group")]

    def opted_in_members(self, limit: int = 100, *, source: str | None = None, offset: int = 0):
        sql = "SELECT * FROM members WHERE consent_status='opted_in' AND is_bot=0 AND is_deleted=0"
        args: list[object] = []
        if source:
            sql += " AND source_group=?"
            args.append(source)
        sql += " ORDER BY id LIMIT ? OFFSET ?"
        args.extend([int(limit), max(0, int(offset))])
        with self.connect() as con:
            return con.execute(sql, args).fetchall()

    def set_consent(self, member_id: int, status: str, note: str = "") -> None:
        if status not in {"unknown", "opted_in", "opted_out"}:
            raise ValueError("invalid consent status")
        with self.connect() as con:
            con.execute(
                "UPDATE members SET consent_status=?,consent_note=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, note, member_id),
            )

    def update_member_result(self, member_id: int, status: str, error: str = "") -> None:
        if status not in {"Pending", "Invited", "Messaged", "Failed", "Skipped"}:
            raise ValueError("invalid member status")
        with self.connect() as con:
            con.execute(
                "UPDATE members SET status=?,last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, error, member_id),
            )

    def import_csv(self, path: str) -> int:
        grouped: dict[tuple[str, bool], list[dict]] = {}
        with open(path, newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                if not row.get("user_id"):
                    continue
                normalized = self.normalize_import_row(row)
                source = str(row.get("source_group") or "import")
                managed = bool(normalized.pop("source_managed", False))
                grouped.setdefault((source, managed), []).append(normalized)
        return sum(
            self.save_members(items, source, managed)
            for (source, managed), items in grouped.items()
        )

    @staticmethod
    def normalize_import_row(row: dict) -> dict:
        def as_bool(value) -> bool:
            return str(value or "0").strip().lower() in {"1", "true", "yes", "y"}

        access_hash = row.get("access_hash")
        return {
            "user_id": int(row["user_id"]),
            "access_hash": int(access_hash) if access_hash not in (None, "") else None,
            "username": str(row.get("username") or ""),
            "first_name": str(row.get("first_name") or ""),
            "last_name": str(row.get("last_name") or ""),
            "phone": str(row.get("phone") or ""),
            "is_bot": as_bool(row.get("is_bot")),
            "is_deleted": as_bool(row.get("is_deleted")),
            "has_photo": as_bool(row.get("has_photo")),
            "last_seen": str(row.get("last_seen") or ""),
            "source_managed": as_bool(row.get("source_managed")),
            "consent_status": str(row.get("consent_status") or "unknown"),
            "consent_note": str(row.get("consent_note") or ""),
        }

    # ---------- jobs and logs ----------
    def create_job(self, job_type: str, account_id: int | None, target: str, total: int) -> int:
        with self.connect() as con:
            cur = con.execute(
                "INSERT INTO jobs(job_type,account_id,target,total,state) VALUES(?,?,?,?, 'Running')",
                (job_type, account_id, target, int(total)),
            )
            return int(cur.lastrowid)

    def finish_job(
        self, job_id: int, success: int, failed: int, skipped: int,
        note: str = "", state: str = "Finished",
    ) -> None:
        if state not in {"Finished", "Failed", "Cancelled"}:
            raise ValueError("invalid job state")
        with self.connect() as con:
            con.execute(
                """UPDATE jobs SET state=?,success=?,failed=?,skipped=?,note=?,finished_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (state, int(success), int(failed), int(skipped), note, job_id),
            )

    def jobs(self, limit: int = 200):
        with self.connect() as con:
            return con.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()

    def log(
        self, job_id: int | None, action_type: str, phone: str, target: str, outcome: str,
        user_id: int | None = None, username: str = "", error_code: str = "", detail: str = "",
    ) -> None:
        with self.connect() as con:
            con.execute(
                """INSERT INTO action_log(job_id,action_type,account_phone,target,user_id,username,outcome,error_code,detail)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (job_id, action_type, phone, target, user_id, username, outcome, error_code, detail),
            )

    def logs(self, limit: int = 500):
        with self.connect() as con:
            return con.execute("SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()

    def stats(self) -> dict[str, int]:
        with self.connect() as con:
            return {
                "accounts": int(con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]),
                "members": int(con.execute("SELECT COUNT(*) FROM members").fetchone()[0]),
                "opted_in": int(con.execute("SELECT COUNT(*) FROM members WHERE consent_status='opted_in'").fetchone()[0]),
                "jobs": int(con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]),
                "success_actions": int(con.execute("SELECT COUNT(*) FROM action_log WHERE outcome='Success'").fetchone()[0]),
            }
