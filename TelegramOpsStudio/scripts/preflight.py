from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "main.py",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    ".github/workflows/windows-build.yml",
    "app/config.py",
    "app/db.py",
    "app/ui.py",
    "app/telegram_service.py",
    "scripts/build_windows.ps1",
    "scripts/check_version.py",
]
FORBIDDEN_SUFFIXES = {".session", ".sqlite", ".sqlite3", ".db", ".pfx", ".p12", ".pem", ".key"}


def main() -> int:
    missing = [item for item in REQUIRED if not (ROOT / item).exists()]
    if missing:
        raise SystemExit(f"Missing required files: {missing}")

    forbidden = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", ".venv", "dist", "build", "__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name.endswith(".session-journal"):
            forbidden.append(str(path.relative_to(ROOT)))
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    if forbidden:
        raise SystemExit(f"Sensitive/runtime files must not be committed: {forbidden}")

    print("PREFLIGHT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
