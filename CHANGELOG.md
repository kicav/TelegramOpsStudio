# Changelog

## 0.4.0.dev0 - Phase 1 functional expansion
- Added saved-session health checks from Accounts.
- Added Groups & Scan History page backed by persisted source records.
- Added Members & Consent catalog with search and consent filtering.
- Added bulk local consent metadata updates: UNKNOWN / OPTED_IN / OPTED_OUT.
- Added migration 0002 for consent state, notes, and index.
- Source scan completion now refreshes group history and member catalog.
- Kept production Telegram access read/validation-first; no bulk membership executor enabled.

## 0.4.0.dev0

- Replaced placeholder Accounts/Workflow/Jobs/Logs/Settings pages with functional PySide6 pages.
- Added command/event contracts for account authentication, source scan, target preview, export and review jobs.
- Added OS-keyring-backed API Hash storage and interactive OTP/2FA login flow.
- Connected accessible Telethon member scans to SQLite with live progress events.
- Added candidate table, filters, target snapshot subtraction and full-set CSV/XLSX export.
- Added persistent review jobs and audit-log browsing in the UI.
- Moved self-check into Settings/Diagnostics and removed developer toolbar controls from the main workflow.
- Preserved read/validation-first production Telegram boundary; no live bulk membership executor is enabled.
- Expanded regression suite to 22 tests, including account/profile joins and >900-member chunked export.

## 0.2.0.dev0

- Standardized application branding as TelegramOpsStudio.
- Kept Qt UI and core asyncio runtime separated by QThread.
- Made CoreRuntime the owner of the application SQLite connection.
- Completed repositories for API profiles, accounts, members, sources, targets, snapshots, jobs, attempts, settings and audit.
- Added batch source scanning and batch target snapshots.
- Added filter engine with explicit UNKNOWN activity handling.
- Added candidate builder and immutable job configuration.
- Added atomic persistent queue claims, leases, retry scheduling and state-transition validation.
- Added attempt-aware crash recovery with remote-verification hook.
- Added fake authorized action adapter and safe end-to-end demo workflow.
- Added read-only Telethon session/entity/member/permission adapter and interactive authentication helper.
- Added CSV/XLSX result export.
- Added OS-backed secret-store abstraction.
- Added dashboard shell and runtime status events.
- Added Windows standalone bundle, Inno Setup installer and GitHub release workflow.
- Expanded automated tests to 16 cases plus 100k-member/100k-queue scale validation.

## 0.1.0.dev0

- Initial M0 repository, migrations, PySide6 shell, fake adapter and CI skeleton.
