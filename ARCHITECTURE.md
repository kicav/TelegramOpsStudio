# TelegramOpsStudio Architecture

## 1. Design rules

1. The Qt main thread owns widgets only.
2. `CoreRuntime` owns the application SQLite connection and background asyncio loop.
3. UI-to-core communication is command/event based; UI does not call Telethon or write the application DB.
4. `telegram_user_id` is the canonical member identity. Username is mutable metadata.
5. Source membership is many-to-many through `source_members`.
6. Target membership is versioned through `target_snapshots` + `target_snapshot_members`.
7. A job is an immutable snapshot of source, target, target snapshot, filter configuration, account selection, range and limit.
8. `job_members` is the durable queue. Queue state is not reconstructed from Excel/CSV.
9. READY → PROCESSING claims are atomic and leased.
10. Remote ambiguity after a crash is verified when possible before recovery changes local state.
11. Server restrictions are state/policy signals. They are not bypassed by account/proxy rotation.
12. Member lists are scanned only when Telegram exposes them to the authenticated account.

## 2. Runtime

```text
┌─────────────────────────────┐
│          Qt UI Thread       │
│  MainWindow / pages / VM    │
└──────────────┬──────────────┘
               │ Commands / Events
               ▼
┌─────────────────────────────┐
│      CoreRuntime QThread    │
│        asyncio loop         │
│                             │
│ SQLite   Scheduler  Adapter │
└─────────────────────────────┘
```

`CoreRuntime` opens `%LOCALAPPDATA%/TelegramOpsStudio/data/app.db` on Windows, applies migrations, then announces `RuntimeReadyEvent`.

## 3. Database

The initial schema contains 14 logical tables:

- `schema_migrations`
- `api_profiles`
- `accounts`
- `members`
- `sources`
- `source_members`
- `targets`
- `target_snapshots`
- `target_snapshot_members`
- `jobs`
- `job_members`
- `attempts`
- `audit_log`
- `settings`

SQLite starts with foreign keys, WAL mode, and a busy timeout.

## 4. Source scan

```text
identifier
  → resolve entity
  → accessible participant iterator
  → normalize TelegramMember
  → batch upsert members
  → batch source_members links
  → progress
  → COMPLETE / PARTIAL / FAILED
```

The scanner does not collect recent message senders as a replacement for a hidden participant list.

## 5. Candidate set

```text
SourceMembers
  → FilterEngine
  → remove bots/deleted according to config
  → subtract TargetSnapshot
  → subtract PreviousSuccess
  → range/limit
  → CandidatePreview + immutable Job
```

Unknown activity is represented as `UNKNOWN`; it is never silently converted to offline/inactive.

## 6. Job member state machine

```text
CANDIDATE → READY → PROCESSING
                      ├── SUCCESS
                      ├── SKIPPED
                      ├── RETRY_WAIT → READY
                      └── FINAL_FAIL
```

A claim uses `BEGIN IMMEDIATE`, selects one eligible READY row, changes it to PROCESSING and commits before any awaited operation begins.

## 7. Job state machine

```text
DRAFT → VALIDATING → READY → RUNNING → COMPLETING → COMPLETED
                            │
                            ├→ PAUSING → PAUSED → RUNNING
                            └→ CANCELLING → CANCELLED
```

Invalid transitions raise `InvalidStateTransition`.

## 8. Attempts and recovery

Every attempted side effect gets an `attempts` row before execution. Terminal/retry state is committed afterward.

For expired PROCESSING rows, `RecoveryManager` asks the action adapter to verify the remote result:

- verified success → `SUCCESS`
- verified false → `READY`
- unverifiable → `READY` under conservative retry policy

If there is an unfinished attempt row, recovery closes it with a structured recovery result.

## 9. Telegram boundary

`TelethonReadOnlyAdapter` implements:

- session health check
- entity resolution
- accessible participant iteration
- target permission validation
- graceful disconnect

`AuthorizedActionAdapter` is a separate interface used by the persistent job runner. The repository ships a fake implementation for CI and controlled tests; the production Telethon adapter is not wired to bulk side effects.

## 10. Secrets

DB rows store references such as `api_hash_secret_ref`, not API hashes or OTP/2FA values. `KeyringSecretStore` uses the OS credential backend. Session files remain outside the DB and are excluded from Git.
