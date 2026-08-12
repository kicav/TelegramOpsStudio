from __future__ import annotations

import csv
from pathlib import Path
from openpyxl import Workbook, load_workbook

FIELDS = ["user_id","access_hash","username","first_name","last_name","phone","is_bot","is_deleted",
          "last_seen","source_group","source_managed","consent_status","consent_note","status","last_error"]


def export_csv(rows, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row[k] if k in row.keys() else "" for k in FIELDS})


def export_xlsx(rows, path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Members"
    ws.append(FIELDS)
    for row in rows:
        ws.append([row[k] if k in row.keys() else "" for k in FIELDS])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col in ws.columns:
        width = max(10, min(38, max(len(str(c.value or "")) for c in col) + 2))
        ws.column_dimensions[col[0].column_letter].width = width
    wb.save(path)


def import_xlsx(path: str) -> list[dict]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    headers = [str(x or "") for x in next(it)]
    out = []
    for vals in it:
        out.append(dict(zip(headers, vals)))
    return out
