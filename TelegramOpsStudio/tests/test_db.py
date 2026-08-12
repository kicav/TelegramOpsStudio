from __future__ import annotations

from pathlib import Path

import pytest

from app.db import Database


def test_member_consent_filters_and_stats(tmp_path: Path):
    db = Database(tmp_path / "app.sqlite3")
    db.save_members(
        [
            {"user_id": 1, "access_hash": 2, "username": "alice", "has_photo": True},
            {"user_id": 2, "access_hash": 3, "username": "bot", "is_bot": True},
        ],
        "managed",
        True,
    )
    rows = db.member_rows()
    assert len(rows) == 2
    assert rows[0]["consent_status"] == "unknown"
    db.set_consent(rows[0]["id"], "opted_in", "test")
    assert db.opted_in_members(10)[0]["user_id"] == 1
    assert len(db.member_rows(bots=False)) == 1
    assert len(db.member_rows(photo_filter="has_photo")) == 1
    assert db.stats()["members"] == 2
    assert db.stats()["opted_in"] == 1


def test_proxy_account_and_daily_counter(tmp_path: Path):
    db = Database(tmp_path / "app.sqlite3")
    proxy_id = db.add_proxy("socks5", "127.0.0.1", 1080, "u", "local")
    account_id = db.add_account("+84000000000", 12345, str(tmp_path / "session"), username="test")
    db.assign_proxy(account_id, proxy_id)
    account = db.account(account_id)
    assert account["proxy_host"] == "127.0.0.1"
    assert db.account_daily_invite_count(account_id) == 0
    db.increment_account_counter(account_id, invites=1, messages=2)
    account = db.account(account_id)
    assert account["invite_success_total"] == 1
    assert account["message_success_total"] == 2
    assert db.account_daily_invite_count(account_id) == 1


def test_job_failure_is_persisted(tmp_path: Path):
    db = Database(tmp_path / "app.sqlite3")
    job_id = db.create_job("Test", None, "target", 1)
    db.finish_job(job_id, 0, 1, 0, "boom", "Failed")
    job = db.jobs(1)[0]
    assert job["state"] == "Failed"
    assert job["note"] == "boom"


def test_invalid_values_are_rejected(tmp_path: Path):
    db = Database(tmp_path / "app.sqlite3")
    with pytest.raises(ValueError):
        db.add_proxy("bad", "localhost", 1080)
    with pytest.raises(ValueError):
        db.set_consent(1, "invalid")


def test_csv_import_preserves_source_managed(tmp_path: Path):
    db = Database(tmp_path / "source.sqlite3")
    csv_path = tmp_path / "members.csv"
    csv_path.write_text(
        "user_id,access_hash,username,source_group,source_managed,consent_status\n"
        "77,88,user77,managed-source,1,opted_in\n",
        encoding="utf-8",
    )
    assert db.import_csv(str(csv_path)) == 1
    row = db.member_rows()[0]
    assert row["source_group"] == "managed-source"
    assert row["source_managed"] == 1
    assert row["consent_status"] == "opted_in"
