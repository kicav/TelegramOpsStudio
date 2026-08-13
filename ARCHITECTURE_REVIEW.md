# Architecture Review — 0.2.0.dev0

## Critical issues found and corrected

### 1. Repository root mismatch

The GitHub repository had the application under `telegram-workflow-desktop/` while root workflows executed `pip install -e .`. That caused CI and Windows builds to fail before tests. The rebuilt artifact is root-clean.

### 2. Source/target identity comparison

The earlier draft compared `source_id == target_id`. These IDs belong to different tables and can both equal `1` while referring to different Telegram entities. The rebuilt `JobRepository` compares resolved `telegram_entity_id` values instead.

### 3. Lease/retry timestamp format

Leases were stored as ISO strings containing `T`/timezone offsets while queries compared them with SQLite `datetime('now')` strings. Text comparison could be wrong. Queue deadlines now use SQLite-compatible UTC text format.

### 4. Attempt numbering after target/account pause

An attempted item could be released back to READY without incrementing `attempt_count`, allowing the next attempt to reuse the same `(job_member_id, attempt_no)` and violate the unique constraint. Release after an actual attempt now increments the counter; crash recovery release does not.

### 5. Unenforced state transitions

Jobs could previously jump between arbitrary states. A domain state machine now rejects invalid transitions.

### 6. Terminal job-member writes from wrong state

`complete()` and `schedule_retry()` could previously update any row. They now require the row to be PROCESSING, preserving READY → PROCESSING → terminal/retry semantics.

### 7. Crash recovery attempt history

Recovery previously changed `job_members` without closing an unfinished `attempts` row. Recovery now attempts to close the latest open attempt with a structured recovery result before changing the queue state.

### 8. Target snapshot memory growth

The earlier target snapshot path accumulated all members in memory. It is now batch-persisted like source scanning.

### 9. Activity ambiguity

Unknown last-seen/activity information now has explicit `ActivityQuality.UNKNOWN`. Filters cannot silently classify it as offline.

### 10. Incomplete repository layer

M0 only implemented member persistence. Repositories now cover API profiles, accounts, sources, targets, snapshots, jobs, job members, attempts, audit and settings.

### 11. Build output ambiguity

The standalone compiler's internal output folder name is no longer treated as the release contract. `scripts/build.ps1` normalizes the final bundle to `release/TelegramOpsStudio/`, self-checks it, and strips PDB files.

### 12. Branding drift

UI/build/package/release names are standardized on `TelegramOpsStudio`; the internal Python package remains `telegram_workflow` to avoid unnecessary migration risk.

## Validation results

- 20/20 automated tests PASS.
- Python compile PASS.
- Safe fake end-to-end workflow PASS.
- 14-table schema PASS.
- `PRAGMA quick_check` PASS.
- `PRAGMA foreign_key_check` returns no violations.
- 100,000-member synthetic upsert PASS.
- 100,000-row durable queue enqueue/claim PASS.
- 3 GitHub workflow YAML files parse successfully.

## Deliberate production boundary

The live Telethon implementation is read-only. It supports session health, entity resolution, accessible participant scans and permission validation. The durable side-effect runner is tested through `AuthorizedActionAdapter` and `FakeTelegramAdapter`; live bulk membership/messaging behavior is intentionally not implemented.
