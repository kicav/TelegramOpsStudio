# Telegram Ops Studio — Final Product Specification 1.0.0

## Stack

- Python 3.13
- PySide6 desktop UI
- Telethon 1.44 user-session client
- SQLite local state/log store
- OS keyring for API Hash and proxy passwords
- openpyxl for XLSX
- Nuitka one-file Windows build
- GitHub Actions CI/release

## Functional flow

```text
Accounts / Sessions
        ↓
Group discovery / resolver
        ↓
Managed Scanner ──→ SQLite ──→ CSV/XLSX
                         ↓
                    Filter/Consent
                         ↓
              ┌──────────┴──────────┐
              ↓                     ↓
        Invite Queue           Messaging
              ↓                     ↓
           Logs/Jobs/Counters/Settings
```

Parallel managed-group tooling:

```text
Join/Leave
Proxy Pool
Get Messages + Media Archive
Seeding/Script with reply/file/delay
Managed multi-group broadcast
License metadata + verified updater
```

## Completeness notes

Features observed across the analyzed tools were retained as product surfaces where they can be operated within permissions: session management, member discovery/store/filter, Excel/CSV exchange, account counters, proxy pool, invite queue, group/user messaging, join/leave, message extraction/media, script sequencing, logs, settings, license/update and Windows packaging.

The product deliberately does not implement account/proxy rotation to evade FloodWait or other Telegram restrictions, and does not enable detailed scraping/mass messaging of arbitrary unmanaged communities.
