# Telegram Ops Studio 1.0.0 — Validation Report

## Completed in the build workspace

- Repository preflight: PASS
- Application/pyproject version consistency: PASS (`1.0.0`)
- Python compile check for `main.py`, `app/`, `scripts/`, `tests/`: PASS
- Database, migration-facing behavior, filters, consent, counters and jobs: tested
- CSV/XLSX round trip including managed-source metadata: tested
- HTTPS updater validation, semantic version comparison and SHA-256 verification: tested
- Source runtime self-test: PASS
- No runtime database/session/private-key files are included in the release source tree

Local result before packaging: **12 passed, 2 skipped**. The skipped tests require PySide6/Telethon, which are intentionally not installed in this Linux/offline build workspace.

## Enforced by GitHub Actions on Windows

The repository workflow does not skip those dependencies. It installs the pinned runtime, then requires all of the following before an artifact is published:

1. layout/preflight/version checks,
2. `pip check`,
3. source compile check,
4. PySide6 + Telethon import smoke test,
5. full pytest including Qt offscreen UI construction and Telethon helper tests,
6. source runtime and offscreen full-UI self-tests,
7. Nuitka one-file build using MSVC,
8. execution of the built EXE runtime self-test and full offscreen UI construction self-test,
9. SHA-256 generation.

A failed step prevents the normal Windows artifact/release from being produced.

## External behavior

Live Telegram operations cannot be proven without the operator's own API credentials, authorized session, network connectivity and target permissions. The program treats Telegram server errors as runtime results and does not bypass server-side restrictions.
