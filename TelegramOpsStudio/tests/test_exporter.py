from __future__ import annotations

from pathlib import Path

from app.db import Database
from app.exporter import export_csv, export_xlsx, import_xlsx


def test_csv_and_xlsx_round_trip(tmp_path: Path):
    db = Database(tmp_path / "source.sqlite3")
    db.save_members(
        [{
            "user_id": 10,
            "access_hash": 20,
            "username": "demo",
            "first_name": "Demo",
            "has_photo": True,
            "consent_status": "opted_in",
        }],
        "group-a",
        True,
    )
    csv_path = tmp_path / "members.csv"
    xlsx_path = tmp_path / "members.xlsx"
    export_csv(db.member_rows(), str(csv_path))
    export_xlsx(db.member_rows(), str(xlsx_path))
    assert csv_path.exists() and csv_path.stat().st_size > 0
    imported_xlsx = import_xlsx(str(xlsx_path))
    assert imported_xlsx[0]["user_id"] == 10

    db2 = Database(tmp_path / "target.sqlite3")
    assert db2.import_csv(str(csv_path)) == 1
    assert db2.member_rows()[0]["username"] == "demo"
