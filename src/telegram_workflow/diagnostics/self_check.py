from __future__ import annotations

import json
import platform
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from telegram_workflow.storage.database import Database
from telegram_workflow.version import __version__

from .paths import ensure_runtime_dirs


@dataclass(frozen=True, slots=True)
class CheckResult:
    ok: bool
    name: str
    detail: str


def run_self_check() -> tuple[bool, list[CheckResult]]:
    results: list[CheckResult] = []

    try:
        paths = ensure_runtime_dirs()
        probe = paths["cache"] / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        results.append(CheckResult(True, "runtime_directories", str(paths["root"])))
    except OSError as exc:
        results.append(CheckResult(False, "runtime_directories", str(exc)))

    try:
        with tempfile.TemporaryDirectory(prefix="telegram-ops-studio-check-") as tmp:
            db_path = Path(tmp) / "selfcheck.db"
            with Database(db_path) as database:
                applied = database.migrate()
                quick_check = database.quick_check()
            ok = quick_check == "ok"
            results.append(
                CheckResult(ok, "sqlite", f"quick_check={quick_check}; migrations={applied}")
            )
    except Exception as exc:  # diagnostic boundary intentionally captures all failures
        results.append(CheckResult(False, "sqlite", f"{type(exc).__name__}: {exc}"))

    try:
        import PySide6
        from PySide6 import QtCore, QtWidgets

        version = getattr(PySide6, "__version__", "unknown")
        detail = f"{version}; Qt={QtCore.qVersion()}; QtWidgets={QtWidgets.__name__}"
        results.append(CheckResult(True, "pyside6", detail))
    except Exception as exc:
        results.append(CheckResult(False, "pyside6", f"{type(exc).__name__}: {exc}"))

    for package_name in ("telethon", "openpyxl", "keyring"):
        try:
            module = __import__(package_name)
            version = getattr(module, "__version__", "available")
            results.append(CheckResult(True, package_name, str(version)))
        except Exception as exc:
            results.append(CheckResult(False, package_name, f"{type(exc).__name__}: {exc}"))

    results.append(CheckResult(True, "python", platform.python_version()))
    results.append(CheckResult(True, "app_version", __version__))
    return all(item.ok for item in results), results


def format_self_check_json(results: list[CheckResult]) -> str:
    return json.dumps([asdict(item) for item in results], indent=2, ensure_ascii=False)
