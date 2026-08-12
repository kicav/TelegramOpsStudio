from __future__ import annotations

import csv
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import DB_PATH, DEFAULTS, ensure_dirs

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
    proxy_type TEXT DEFAULT '',
    proxy_host TEXT DEFAULT '',
    proxy_port INTEGER DEFAULT 0,
    proxy_user TEXT DEFAULT '',
    proxy_pass TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TEXT
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
    state TEXT NOT NULL DEFAULT 'Queued',
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

CREATE TABLE IF NOT EXISTS proxies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proxy_type TEXT NOT NULL DEFAULT 'socks5',
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    username TEXT DEFAULT '',
    password TEXT DEFAULT '',
    label TEXT DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    UNIQUE(proxy_type, host, port, username)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path | str = DB_PATH):
        ensure_dirs()
        self.path = str(path)
        with self.connect() as con:
            con.executescript(SCHEMA)
            for k, v in DEFAULTS.items():
                con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()


    def add_proxy(self, proxy_type: str, host: str, port: int, username: str = "", password: str = "", label: str = "") -> None:
        with self.connect() as con:
            con.execute("""INSERT INTO proxies(proxy_type,host,port,username,password,label) VALUES(?,?,?,?,?,?)
                ON CONFLICT(proxy_type,host,port,username) DO UPDATE SET password=excluded.password,label=excluded.label,enabled=1""",
                (proxy_type,host,int(port),username,password,label))

    def proxies(self):
        with self.connect() as con:
            return con.execute("SELECT * FROM proxies ORDER BY id").fetchall()

    def delete_proxy(self, proxy_id: int) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM proxies WHERE id=?", (proxy_id,))

    def assign_proxy(self, account_id: int, proxy_id: int) -> None:
        with self.connect() as con:
            p=con.execute("SELECT * FROM proxies WHERE id=? AND enabled=1", (proxy_id,)).fetchone()
            if not p:
                raise ValueError("Proxy not found")
            con.execute("""UPDATE accounts SET proxy_type=?,proxy_host=?,proxy_port=?,proxy_user=?,proxy_pass=? WHERE id=?""",
                        (p["proxy_type"],p["host"],p["port"],p["username"],p["password"],account_id))

    def add_account(self, phone: str, api_id: int, session_file: str, **meta) -> int:
        with self.connect() as con:
            con.execute(
                """INSERT INTO accounts(phone,api_id,session_file,display_name,username,status,
                   proxy_type,proxy_host,proxy_port,proxy_user,proxy_pass)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(phone) DO UPDATE SET
                   api_id=excluded.api_id, session_file=excluded.session_file,
                   display_name=excluded.display_name, username=excluded.username,
                   status=excluded.status""",
                (phone, api_id, session_file, meta.get("display_name", ""), meta.get("username", ""),
                 meta.get("status", "Authorized"), meta.get("proxy_type", ""), meta.get("proxy_host", ""),
                 int(meta.get("proxy_port", 0) or 0), meta.get("proxy_user", ""), meta.get("proxy_pass", "")),
            )
            return int(con.execute("SELECT id FROM accounts WHERE phone=?", (phone,)).fetchone()[0])

    def update_proxy(self, account_id: int, proxy_type: str, host: str, port: int, user: str = "", password: str = "") -> None:
        with self.connect() as con:
            con.execute("""UPDATE accounts SET proxy_type=?,proxy_host=?,proxy_port=?,proxy_user=?,proxy_pass=? WHERE id=?""",
                        (proxy_type, host, port, user, password, account_id))

    def delete_account(self, account_id: int) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM accounts WHERE id=?", (account_id,))

    def accounts(self):
        with self.connect() as con:
            return con.execute("SELECT * FROM accounts ORDER BY id").fetchall()

    def account(self, account_id: int):
        with self.connect() as con:
            return con.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()

    def upsert_group(self, account_id: int, peer_id: int | None, title: str, identifier: str,
                     is_managed: bool, participant_count: int | None) -> None:
        with self.connect() as con:
            con.execute("""INSERT INTO groups(account_id,peer_id,title,identifier,is_managed,participant_count,scanned_at)
                VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(account_id,identifier) DO UPDATE SET
                peer_id=excluded.peer_id,title=excluded.title,is_managed=excluded.is_managed,
                participant_count=excluded.participant_count,scanned_at=CURRENT_TIMESTAMP""",
                (account_id, peer_id, title, identifier, int(is_managed), participant_count or 0))

    def save_members(self, rows: Iterable[dict], source_group: str, source_managed: bool = True) -> int:
        count = 0
        with self.connect() as con:
            for m in rows:
                con.execute("""INSERT INTO members(user_id,access_hash,username,first_name,last_name,phone,
                    is_bot,is_deleted,last_seen,source_group,source_managed,consent_status,consent_note)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(user_id,source_group) DO UPDATE SET
                    access_hash=excluded.access_hash, username=excluded.username, first_name=excluded.first_name,
                    last_name=excluded.last_name, phone=excluded.phone, is_bot=excluded.is_bot,
                    is_deleted=excluded.is_deleted,last_seen=excluded.last_seen,
                    source_managed=excluded.source_managed,updated_at=CURRENT_TIMESTAMP""",
                    (m["user_id"], m.get("access_hash"), m.get("username", ""), m.get("first_name", ""),
                     m.get("last_name", ""), m.get("phone", ""), int(bool(m.get("is_bot"))),
                     int(bool(m.get("is_deleted"))), m.get("last_seen", ""), source_group,
                     int(source_managed), m.get("consent_status", "unknown"), m.get("consent_note", "")))
                count += 1
        return count

    def member_rows(self, *, bots=True, deleted=True, consent: str | None = None, source: str | None = None):
        sql = "SELECT * FROM members WHERE 1=1"
        args: list[object] = []
        if not bots:
            sql += " AND is_bot=0"
        if not deleted:
            sql += " AND is_deleted=0"
        if consent:
            sql += " AND consent_status=?"; args.append(consent)
        if source:
            sql += " AND source_group=?"; args.append(source)
        sql += " ORDER BY id"
        with self.connect() as con:
            return con.execute(sql, args).fetchall()

    def opted_in_members(self, limit: int = 100):
        with self.connect() as con:
            return con.execute("""SELECT * FROM members WHERE consent_status='opted_in'
                AND is_bot=0 AND is_deleted=0 ORDER BY id LIMIT ?""", (limit,)).fetchall()

    def set_consent(self, member_id: int, status: str, note: str = "") -> None:
        if status not in {"unknown", "opted_in", "opted_out"}:
            raise ValueError("invalid consent status")
        with self.connect() as con:
            con.execute("UPDATE members SET consent_status=?, consent_note=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (status, note, member_id))

    def update_member_result(self, member_id: int, status: str, error: str = "") -> None:
        with self.connect() as con:
            con.execute("UPDATE members SET status=?,last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (status, error, member_id))

    def create_job(self, job_type: str, account_id: int | None, target: str, total: int) -> int:
        with self.connect() as con:
            cur = con.execute("INSERT INTO jobs(job_type,account_id,target,total,state) VALUES(?,?,?,?, 'Running')",
                              (job_type, account_id, target, total))
            return int(cur.lastrowid)

    def finish_job(self, job_id: int, success: int, failed: int, skipped: int, note: str = "") -> None:
        with self.connect() as con:
            con.execute("""UPDATE jobs SET state='Finished',success=?,failed=?,skipped=?,note=?,finished_at=CURRENT_TIMESTAMP WHERE id=?""",
                        (success, failed, skipped, note, job_id))

    def log(self, job_id: int | None, action_type: str, phone: str, target: str, outcome: str,
            user_id: int | None = None, username: str = "", error_code: str = "", detail: str = "") -> None:
        with self.connect() as con:
            con.execute("""INSERT INTO action_log(job_id,action_type,account_phone,target,user_id,username,outcome,error_code,detail)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (job_id, action_type, phone, target, user_id, username, outcome, error_code, detail))

    def stats(self) -> dict:
        with self.connect() as con:
            return {
                "accounts": con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0],
                "members": con.execute("SELECT COUNT(*) FROM members").fetchone()[0],
                "opted_in": con.execute("SELECT COUNT(*) FROM members WHERE consent_status='opted_in'").fetchone()[0],
                "jobs": con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
                "success_actions": con.execute("SELECT COUNT(*) FROM action_log WHERE outcome='Success'").fetchone()[0],
            }

    def logs(self, limit: int = 500):
        with self.connect() as con:
            return con.execute("SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def get_setting(self, key: str, default: str = "") -> str:
        with self.connect() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as con:
            con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

    def import_csv(self, path: str) -> int:
        count = 0
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = csv.DictReader(f)
            grouped: dict[str, list[dict]] = {}
            for r in rows:
                if not r.get("user_id"):
                    continue
                source = r.get("source_group", "import")
                grouped.setdefault(source, []).append({
                    "user_id": int(r["user_id"]),
                    "access_hash": int(r["access_hash"]) if r.get("access_hash") else None,
                    "username": r.get("username", ""), "first_name": r.get("first_name", ""),
                    "last_name": r.get("last_name", ""), "phone": r.get("phone", ""),
                    "is_bot": str(r.get("is_bot", "0")).lower() in {"1", "true", "yes"},
                    "is_deleted": str(r.get("is_deleted", "0")).lower() in {"1", "true", "yes"},
                    "last_seen": r.get("last_seen", ""),
                    "consent_status": r.get("consent_status", "unknown") if r.get("consent_status", "unknown") in {"unknown","opted_in","opted_out"} else "unknown",
                    "consent_note": r.get("consent_note", ""),
                })
            for source, ms in grouped.items():
                count += self.save_members(ms, source, source_managed=False)
        return count
