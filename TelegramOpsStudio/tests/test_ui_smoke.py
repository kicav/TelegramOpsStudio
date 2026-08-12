from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("telethon")
pytest.importorskip("socks")
pytest.importorskip("keyring")

from PySide6.QtWidgets import QApplication

from app.db import Database
from app.ui import MainWindow


def test_main_window_constructs(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Database(tmp_path / "ui.sqlite3"))
    assert window.windowTitle().startswith("Telegram Ops Studio")
    assert window.centralWidget().count() == 12
    window.close()
    app.processEvents()
