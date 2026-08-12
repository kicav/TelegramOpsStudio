# Telegram Workflow Desktop

Desktop workflow engine for permission-aware Telegram account, source-member, target-validation,
job, recovery, audit, and export workflows.

## Architecture

- PySide6/Qt Widgets owns the UI thread.
- `CoreRuntime` owns the background asyncio event loop and all core services.
- UI communicates with core only through commands/events.
- SQLite is the source of truth; CSV/XLSX are import/export formats only.
- Telegram access is abstracted behind `TelegramAdapter`; CI uses a fake adapter and never real accounts.
- Restrictions returned by Telegram are treated as state/policy signals, not something to bypass.

## M0 status

M0 establishes the repository layout, CLI diagnostics, database migrations, a fake Telegram adapter,
minimal runtime bus, tests, and Windows GitHub Actions build skeleton.

## Local development

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
python -m telegram_workflow --self-check
pytest
python -m telegram_workflow
```

## Security

Never commit `.session`, API credentials, OTP/2FA secrets, runtime databases, exports containing
sensitive identifiers, or proxy credentials. Production releases must not include PDB/debug symbols.
