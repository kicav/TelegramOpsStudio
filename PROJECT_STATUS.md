# Project Status

## 0.3.0.dev0 functional milestone

Implemented in this source package:

- functional Accounts page for API profile + Telegram OTP/2FA session authentication;
- API Hash storage through OS keyring, not plaintext SQLite;
- functional Workflow page with account selection, source scan progress and member table;
- filter controls for bot/deleted/username/activity handling;
- target resolution, permission validation and accessible target snapshot;
- candidate subtraction/preview with a 5,000-row UI display cap while retaining the full selected ID set for export/job creation;
- CSV/XLSX candidate export;
- persistent review-job creation and Jobs table;
- audit-backed Logs page;
- Settings/Diagnostics page with runtime paths and self-check;
- technical Ping/Self Check controls removed from the primary production toolbar.

Validation in the current environment:

- Python compilation: PASS
- pytest: 22/22 PASS
- fake end-to-end workflow: PASS
- direct source version: `0.3.0.dev0`

The previous `0.2.0.dev0` baseline has already produced a successful Windows GitHub Actions standalone build. The `0.3.0.dev0` UI/runtime changes must be uploaded and rebuilt on the Windows runner before release.

## Safety boundary

Live Telethon access is authentication/read/validation-first. Review jobs persist the candidate set but no production bulk membership executor is connected. The project contains no hidden-member bypass, FloodWait evasion, restriction avoidance, or account/proxy rotation logic.
