# TelegramOpsStudio

Local-first Windows desktop workflow engine for permission-aware Telegram operations, source-member analytics, target validation, persistent jobs, recovery, audit, and export.

## Current release line

`0.2.0.dev0` is the architecture-complete baseline. The data layer, persistent queue, state machines, scanner, filtering, target snapshots, candidate builder, retry/recovery engine, exports, diagnostics, fake end-to-end workflow, PySide6 shell, and GitHub build/release pipelines are implemented.

The production Telethon adapter is intentionally **read-only**: session health, entity resolution, accessible participant scans, and target permission validation. Side effects are isolated behind `AuthorizedActionAdapter`; CI uses `FakeTelegramAdapter`. There is no participant-list bypass, message-sender fallback, FloodWait evasion, or hidden account rotation.

## Architecture

```text
Qt UI thread
    │ commands/events only
    ▼
CoreRuntime QThread
    │ asyncio loop
    ├── SQLite / migrations / repositories
    ├── account/session services
    ├── source scanner
    ├── filter + candidate builder
    ├── target validator + versioned snapshots
    ├── persistent job queue + attempts
    ├── retry + recovery
    └── TelegramAdapter boundary
```

SQLite is the source of truth. CSV/XLSX are export formats only. Telethon `.session` files are stored separately under the local application-data directory.

## Safe end-to-end validation

The core engine can be tested without Qt or Telegram credentials:

```powershell
python -m telegram_workflow --demo-workflow
```

Expected result: a fake source scan, filter/target subtraction, persistent job, success/skip results, and a `COMPLETED` job.

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

## Windows build

```powershell
./scripts/build.ps1
```

The stable bundle is written to:

```text
release/TelegramOpsStudio/
```

The build script runs `--version` and `--self-check` against the compiled executable and removes PDB files from the release bundle.

## GitHub Actions

- `CI`: compile, Ruff, pytest, self-check on Python 3.12.
- `Build Windows`: clean Windows build with `pyside6-deploy`/Nuitka standalone and artifact upload.
- `Release Windows`: portable ZIP, Inno Setup installer, SHA-256 file, GitHub Release.

See `ARCHITECTURE.md`, `SECURITY.md`, and `DEPLOYMENT.md` for the frozen design and release procedure.
