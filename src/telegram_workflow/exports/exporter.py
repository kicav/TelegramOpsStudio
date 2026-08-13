from __future__ import annotations

import csv
from pathlib import Path


class ResultExporter:
    def __init__(self, connection) -> None:
        self.connection = connection

    def export_job_csv(self, job_id: int, path: Path) -> int:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.connection.execute(
            """
            SELECT m.telegram_user_id, m.username, m.first_name, m.last_name,
                   jm.state, jm.last_error_code, jm.last_error_message,
                   jm.completed_at
            FROM job_members jm
            JOIN members m ON m.id = jm.member_id
            WHERE jm.job_id = ?
            ORDER BY jm.id
            """,
            (job_id,),
        ).fetchall()
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "User ID",
                    "Username",
                    "First Name",
                    "Last Name",
                    "Status",
                    "Reason",
                    "Message",
                    "Completed At",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row["telegram_user_id"],
                        row["username"] or "",
                        row["first_name"],
                        row["last_name"],
                        row["state"],
                        row["last_error_code"] or "",
                        row["last_error_message"] or "",
                        row["completed_at"] or "",
                    ]
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
            [
                "User ID",
                "Username",
                "First Name",
                "Last Name",
                "Status",
                "Reason",
                "Message",
                "Completed At",
            ]
        )
        for row in rows:
            sheet.append(
                [
                    row["telegram_user_id"],
                    row["username"] or "",
                    row["first_name"],
                    row["last_name"],
                    row["state"],
                    row["last_error_code"] or "",
                    row["last_error_message"] or "",
                    row["completed_at"] or "",
                ]
            )
        workbook.save(path)
        return len(rows)

