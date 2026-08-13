# TelegramOpsStudio

Local-first Windows desktop application for permission-aware Telegram account/session management, accessible member scanning, filtering, target snapshots, candidate review, persistent review jobs, audit logs and CSV/XLSX export.

## Current release line

`0.4.0.dev0` is the first functional desktop milestone. The UI is no longer a placeholder shell: Accounts, Workflow, Jobs, Logs and Settings are connected to `CoreRuntime` through commands/events.

The production Telethon boundary remains intentionally **read/validation-first**. It can authenticate sessions, resolve entities, enumerate participant lists Telegram exposes to the authenticated account, inspect target permissions and capture accessible target snapshots. Live bulk membership execution is not enabled. There is no participant-list bypass, message-sender fallback, FloodWait evasion, proxy/account rotation, or hidden-member circumvention.

## Functional workflow

```text
Accounts
  API ID + API Hash + phone
        ↓
  Telegram OTP / optional 2FA
        ↓
  OS credential store + local .session
        ↓
Workflow
  source link → accessible member scan → SQLite
        ↓
  filters
        ↓
  target link → permission validation → target snapshot
        ↓
  remove target overlap / previous success
        ↓
  candidate preview
        ↓
  CSV/XLSX export or persistent review job
```

API Hash values are stored through the operating-system keyring. OTP and 2FA values are never written to SQLite by the authentication service. SQLite remains the canonical data store; spreadsheet files are exports only.

## Architecture

```text
PySide6 UI thread
    │ immutable commands/events
    ▼
CoreRuntime QThread
    │ asyncio loop; owns SQLite + Telegram clients
    ├── keyring secret store
    ├── account/session auth
    ├── source scanner
    ├── filter + candidate builder
    ├── target validator + snapshots
    ├── persistent review jobs
    ├── audit log
    └── CSV/XLSX exporter
```

## Local development

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
./scripts/test.ps1
python -m telegram_workflow --self-check
python -m telegram_workflow
```

A safe fake engine test is also available:

```powershell
python -m telegram_workflow --demo-workflow
```

## Windows build

```powershell
./scripts/build.ps1
```

Output:

```text
release/TelegramOpsStudio/
└── TelegramOpsStudio.exe + required DLL/PYD/package files
```

The whole standalone directory must be distributed together; `TelegramOpsStudio.exe` is not a single-file build.

## GitHub Actions

- `CI`: compile, Ruff, pytest and self-check on Python 3.12.
- `Build Windows`: PySide6/Nuitka standalone build and artifact upload.
- `Release Windows`: portable ZIP, Inno Setup installer and SHA-256 release assets.

See `ARCHITECTURE.md`, `SECURITY.md`, and `DEPLOYMENT.md` for the design and release procedure.
