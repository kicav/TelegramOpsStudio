from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "TelegramOpsStudio"


def app_data_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / APP_DIR_NAME


def runtime_paths() -> dict[str, Path]:
    root = app_data_dir()
    return {
        "root": root,
        "data": root / "data",
        "sessions": root / "sessions",
        "logs": root / "logs",
        "exports": root / "exports",
        "cache": root / "cache",
        "backups": root / "backups",
    }


def ensure_runtime_dirs() -> dict[str, Path]:
    paths = runtime_paths()
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths
