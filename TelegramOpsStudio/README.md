# Telegram Ops Studio

A desktop Telegram operations application rebuilt from the architecture observed in the supplied videos and reverse-engineered installer, but redesigned to be maintainable and permission-aware.

## Included modules

- Dashboard and action logs
- Multiple Telegram user sessions
- OS credential-store protection for API hash
- Proxy Pool with manual per-account SOCKS5/HTTP assignment for connectivity
- Public group overview (aggregate metadata only)
- Detailed member scan for groups administered by the selected account
- SQLite member store (`user_id`, `access_hash`, username, names, phone when available, last-seen category)
- CSV/XLSX import/export
- Local member filtering and explicit consent states (`unknown`, `opted_in`, `opted_out`)
- Consent-based invite queue to a group administered by the selected account
- Group messaging to groups administered by the selected account
- Direct campaigns to opted-in records only
- Single-account Join / Leave module
- Managed-group message archive (message ID, sender, reply relationship, media metadata)
- Managed-group Seeding/Script runner with delays and reply-to mapping
- Settings, structured logs, local license metadata reader, HTTPS+SHA256 update manifest checker
- Windows standalone build script (Nuitka + PySide6)

## Important design differences from the analyzed tools

The analyzed software contained multi-account rotation, proxy pools and bulk workflows that can be used to bypass platform restrictions or contact strangers at scale. This rebuild keeps the product surface but does **not** use account/proxy rotation to evade Telegram restrictions. A `FloodWait` stops the active job. Detailed identity scanning is limited to groups the selected account administers; direct messaging and direct invitation require an explicit `opted_in` consent state.

This is intentional: it preserves the useful engineering architecture without turning the application into an anti-abuse bypass/spam system.

## Install

Recommended: Python 3.13 on Windows 10/11.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

## First run

1. Open **Accounts & Sessions**.
2. Enter your Telegram API ID, API Hash and phone number.
3. Click **Authorize / Add session** and enter the Telegram login code / 2FA if requested.
4. API Hash is stored through the operating-system keyring; the SQLite DB stores account metadata and the local session path.
5. Use **Scanner**:
   - `Public overview`: returns aggregate group metadata.
   - `Detailed scan — managed group`: saves member identities only when the selected account is an administrator/creator.
6. Use **Filter & Consent** to mark imported or managed-group records as opted in.
7. **Invite Queue** starts in `Dry run` mode. Direct invitations require target admin/invite permission and `opted_in` members.
8. **Messaging** group mode requires a managed group; user mode only selects opted-in members.

## Spreadsheet format

CSV/XLSX fields:

`user_id, access_hash, username, first_name, last_name, phone, is_bot, is_deleted, last_seen, source_group, source_managed, consent_status, consent_note, status, last_error`

For imported records, set `consent_status=opted_in` only when you have a legitimate basis to contact/invite the person.

## Database

Runtime data is stored under:

`%USERPROFILE%\\.telegram_ops_studio\\`

- `telegram_ops.sqlite3`
- `sessions/`
- `exports/`

Never share `.session` files. A Telegram session can authorize access without requiring a fresh login code.

## Build Windows standalone

```powershell
.\scripts\build_windows.ps1
```

Do not ship `.pdb` files or hard-code Telegram/licensing secrets in production builds.

## Update manifest

The checker accepts an HTTPS JSON manifest:

```json
{
  "version": "0.2.0",
  "url": "https://example.com/TelegramOpsStudioSetup.exe",
  "sha256": "<64 hex chars>"
}
```

The included helper can verify SHA-256 before staging an update. A production product should additionally verify a digital signature.

## GitHub Actions build

The repository includes `.github/workflows/windows-build.yml`.

- Push to `main`: compile check, unit tests, and Windows `.exe` build.
- Manual build: GitHub → Actions → **Build Windows App** → **Run workflow**.
- Push a `v*` tag: builds the `.exe` and publishes a GitHub Release.

See `GITHUB_BUILD.md` for the exact deployment steps.
