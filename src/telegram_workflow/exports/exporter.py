from __future__ import annotations

import csv
from pathlib import Path


_MEMBER_HEADERS = [
    "User ID", "Username", "First Name", "Last Name", "Phone", "Bot", "Deleted",
    "Last Seen", "Activity Quality",
]


class ResultExporter:
    def __init__(self, connection) -> None:
        self.connection = connection

    def _member_rows(self, member_ids: list[int]):
        if not member_ids:
            return []
        rows = []
        for offset in range(0, len(member_ids), 900):
            chunk = member_ids[offset : offset + 900]
            placeholders = ",".join("?" for _ in chunk)
            rows.extend(
                self.connection.execute(
                    f"""
                    SELECT id, telegram_user_id, username, first_name, last_name, phone,
                           is_bot, is_deleted, last_seen, activity_quality
                    FROM members WHERE id IN ({placeholders})
                    """,
                    chunk,
                ).fetchall()
            )
        rows.sort(key=lambda row: int(row["id"]))
        return rows

    @staticmethod
    def _member_values(row) -> list[object]:
        return [
            row["telegram_user_id"], row["username"] or "", row["first_name"],
            row["last_name"], row["phone"], bool(row["is_bot"]), bool(row["is_deleted"]),
            row["last_seen"] or "", row["activity_quality"],
        ]

    def export_members_csv(self, member_ids: list[int], path: Path) -> int:
        rows = self._member_rows(member_ids)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(_MEMBER_HEADERS)
            for row in rows:
                writer.writerow(self._member_values(row))
        return len(rows)

    def export_members_xlsx(self, member_ids: list[int], path: Path) -> int:
        try:
            from openpyxl import Workbook
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("openpyxl is not installed") from exc
        rows = self._member_rows(member_ids)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Members"
        sheet.append(_MEMBER_HEADERS)
        for row in rows:
            sheet.append(self._member_values(row))
        workbook.save(path)
        return len(rows)

    def export_job_csv(self, job_id: int, path: Path) -> int:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.connection.execute(
            """
            SELECT m.telegram_user_id, m.username, m.first_name, m.last_name,
                   jm.state, jm.last_error_code, jm.last_error_message, jm.completed_at
            FROM job_members jm
            JOIN members m ON m.id = jm.member_id
            WHERE jm.job_id = ? ORDER BY jm.id
            """,
            (job_id,),
        ).fetchall()
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ["User ID", "Username", "First Name", "Last Name", "Status", "Reason",
                 "Message", "Completed At"]
            )
            for row in rows:
                writer.writerow(
                    [row["telegram_user_id"], row["username"] or "", row["first_name"],
                     row["last_name"], row["state"], row["last_error_code"] or "",
                     row["last_error_message"] or "", row["completed_at"] or ""]
                )
        return len(rows)

    def export_job_xlsx(self, job_id: int, path: Path) -> int:
        try:
            from openpyxl import Workbook
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("openpyxl is not installed") from exc
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.connection.execute(
            """
            SELECT m.telegram_user_id, m.username, m.first_name, m.last_name,
                   jm.state, jm.last_error_code, jm.last_error_message, jm.completed_at
            FROM job_members jm
            JOIN members m ON m.id = jm.member_id
            WHERE jm.job_id = ? ORDER BY jm.id
            """,
            (job_id,),
        ).fetchall()
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Job Results"
        sheet.append(
            ["User ID", "Username", "First Name", "Last Name", "Status", "Reason",
             "Message", "Completed At"]
        )
        for row in rows:
            sheet.append(
                [row["telegram_user_id"], row["username"] or "", row["first_name"],
                 row["last_name"], row["state"], row["last_error_code"] or "",
                 row["last_error_message"] or "", row["completed_at"] or ""]
            )
        workbook.save(path)
        return len(rows)
