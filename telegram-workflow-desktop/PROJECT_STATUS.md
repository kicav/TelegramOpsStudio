# Project Status

## Milestone M0 — implemented locally

Completed:

- Frozen `src/` package layout.
- PySide6 shell application and version CLI.
- `--self-check` diagnostics.
- CoreRuntime QThread + background asyncio command/event skeleton.
- Initial 14-table SQLite schema and atomic migration manager.
- Member upsert/dedup repository.
- TelegramAdapter interface and FakeTelegramAdapter test implementation.
- Unit/integration/migration tests.
- Windows standalone build script using `pyside6-deploy` in `standalone` mode.
- CI, manual Windows build, and tag-release GitHub Actions workflows.
- Runtime/session/secrets/build artifacts excluded by `.gitignore`.

Validation in the current execution environment:

- Python source compilation: PASS.
- Pytest: 7/7 PASS.
- GitHub workflow YAML parsing: PASS.
- SQLite migration, atomic rollback and quick_check: PASS.
- 100,000-member synthetic upsert: PASS (100,000 rows, quick_check=ok).
- PySide6 runtime/build: NOT EXECUTED locally because this analysis container does not contain PySide6
  and cannot reach PyPI. The GitHub Windows workflow is designed to perform this validation on a clean runner.

## GitHub blocker

The connected GitHub account currently exposes `kicav/telegram_analytics_dashboard`. The GitHub
connector available in this session can modify existing repositories but cannot create a new repository,
and the local environment does not have an authenticated `gh` executable. The intended repository is:

`kicav/telegram-workflow-desktop`

Once that empty repository exists and is visible to the connector, the prepared M0 source can be
committed there without mixing it into the analytics repository.

## Next milestone

M1: repositories and data-layer contracts for accounts, sources, targets, snapshots, jobs, attempts,
settings and audit logging, followed by atomic job-member claim/recovery tests. No real Telegram
membership action is required for M1.
