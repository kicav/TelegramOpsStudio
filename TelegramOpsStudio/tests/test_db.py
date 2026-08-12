from pathlib import Path
from app.db import Database


def test_member_consent(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")
    db.save_members([{"user_id": 1, "access_hash": 2, "username": "u"}], "managed", True)
    row = db.member_rows()[0]
    assert row["consent_status"] == "unknown"
    db.set_consent(row["id"], "opted_in", "test")
    assert db.opted_in_members(10)[0]["user_id"] == 1


def test_stats(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite")
    assert db.stats()["accounts"] == 0
