# Changelog

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
