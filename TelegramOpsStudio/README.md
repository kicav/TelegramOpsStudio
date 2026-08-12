# Telegram Ops Studio 1.0.0

Windows desktop application built with Python 3.13, PySide6, Telethon and SQLite.

## Included modules

- Dashboard
- Accounts & Telethon sessions (OTP + 2FA)
- Joined-group discovery and group overview
- Detailed member scan for groups administered by the selected account
- SQLite member store with `user_id`, `access_hash`, profile/activity metadata and consent state
- CSV/XLSX import/export
- Filtering by bot/deleted/photo/source/username/activity/consent
- Consent-gated invite queue with source/offset/limit and dry-run
- Managed-group messaging, managed multi-group broadcast and opted-in direct messaging
- Join / Leave
- Proxy pool with per-account assignment; proxy passwords use the OS credential store
- Managed-group message archive, optional media download and CSV export
- Managed-group message scripts with delay, reply mapping and optional file attachment
- Action logs, job history, counters and settings
- Local license metadata inspection
- HTTPS update manifest check and SHA-256 verified update download
- GitHub Actions Windows build to one-file `TelegramOpsStudio.exe`

## Safety boundary

The app does not rotate accounts or proxies after Telegram restrictions and stops jobs on `FloodWait`. Detailed member collection, group broadcasts, archive and scripts are limited to groups administered by the selected account. User-directed invite/message queues require records explicitly marked `opted_in`.

## Run from source on Windows

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pip check
python -m pytest -q
python main.py
```

## Build locally on Windows

Visual Studio 2022 Build Tools must be available for Nuitka/Python 3.13.

```powershell
.\scripts\build_windows.ps1
```

Output:

```text
dist/TelegramOpsStudio.exe
dist/SHA256SUMS.txt
dist/nuitka-report.xml
```

The build script runs both runtime `--self-test` and full offscreen `--ui-self-test` on the resulting executable before declaring success.

## GitHub Actions build

Push the complete repository to `main`. The workflow:

1. validates required files,
2. installs Python 3.13 and all dependencies,
3. runs `pip check`, compile checks, imports and pytest,
4. builds the one-file Windows executable with Nuitka + MSVC,
5. executes source runtime/UI self-tests and then the built EXE runtime/UI self-tests,
6. generates SHA-256,
7. uploads the executable as an Actions artifact,
8. requires a release tag such as `v1.0.0` to match `APP_VERSION`,
9. creates/updates a GitHub Release with the EXE, checksum and `update-manifest.json`.

Do not upload only selected files. `requirements.txt`, `requirements-dev.txt`, `.github/workflows/windows-build.yml`, `app/`, `tests/`, `scripts/` and `main.py` are all required.

## Application data

Default location:

```text
%USERPROFILE%\.telegram_ops_studio\
├── telegram_ops.sqlite3
├── sessions\
├── exports\
└── downloads\
```

API Hash values and proxy passwords are not stored in source or SQLite; they are stored through the operating-system keyring. Telegram `.session` files are excluded by `.gitignore` and must never be committed.

For tests/portable environments, the data directory can be overridden with:

```powershell
$env:TELEGRAM_OPS_DATA_DIR="D:\TelegramOpsData"
```

## First validation order

1. `python -m pytest -q`
2. `python main.py`
3. authorize one test Telegram account
4. test public overview
5. test a managed test group
6. test XLSX/CSV round trip
7. keep Invite Queue in Dry Run for initial validation
8. run local build or push to GitHub Actions

Live Telegram behavior still depends on Telegram permissions, privacy rules, API credentials, account state and network access; CI tests do not bypass server-side rules.

## Stable updater manifest URL

After the first tagged GitHub Release, set **Settings → update_manifest_url** to:

```text
https://github.com/<owner>/<repository>/releases/latest/download/update-manifest.json
```

The release workflow creates this manifest from the built EXE SHA-256. The application still downloads an update to the local downloads folder and verifies it; it does not silently replace a running executable.
