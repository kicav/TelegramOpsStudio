from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Nuitka project defaults. CLI flags in the GitHub workflow may override these.
# nuitka-project: --enable-plugin=pyside6
# nuitka-project: --include-package=keyring.backends
# nuitka-project: --windows-console-mode=disable


def self_test() -> int:
    """Fast runtime test used by CI after building the Windows executable."""
    from app.db import Database
    from app.exporter import export_xlsx, import_xlsx

    with tempfile.TemporaryDirectory(prefix="telegram-ops-selftest-") as tmp:
        root = Path(tmp)
        db = Database(root / "selftest.sqlite3")
        assert db.stats()["accounts"] == 0
        db.save_members(
            [{"user_id": 123, "access_hash": 456, "username": "selftest", "has_photo": True}],
            "selftest-source",
            True,
        )
        row = db.member_rows()[0]
        db.set_consent(row["id"], "opted_in", "self test")
        assert db.opted_in_members(1)[0]["user_id"] == 123
        xlsx = root / "members.xlsx"
        export_xlsx(db.member_rows(), str(xlsx))
        assert import_xlsx(str(xlsx))[0]["user_id"] == 123
    print("TELEGRAM_OPS_SELF_TEST_OK")
    return 0


def ui_self_test() -> int:
    """Construct the full Qt UI without showing it; used by Windows CI/build validation."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from app.db import Database
    from app.ui import MainWindow

    with tempfile.TemporaryDirectory(prefix="telegram-ops-ui-selftest-") as tmp:
        app = QApplication.instance() or QApplication([])
        window = MainWindow(Database(Path(tmp) / "ui.sqlite3"))
        tabs = window.centralWidget()
        if tabs is None or tabs.count() != 12:
            raise RuntimeError("UI self-test expected 12 top-level tabs")
        window.close()
        app.processEvents()
    print("TELEGRAM_OPS_UI_SELF_TEST_OK")
    return 0


def run_gui() -> int:
    from PySide6.QtWidgets import QApplication
    from app.config import APP_DISPLAY_NAME
    from app.ui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    window = MainWindow()
    window.show()
    return app.exec()


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if "--ui-self-test" in sys.argv:
        return ui_self_test()
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
