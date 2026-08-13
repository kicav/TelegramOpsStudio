PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS api_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    api_id INTEGER,
    api_hash_secret_ref TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL UNIQUE,
    username TEXT,
    session_ref TEXT,
    api_profile_id INTEGER REFERENCES api_profiles(id),
    state TEXT NOT NULL DEFAULT 'NEW',
    health_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    last_checked TEXT,
    cooldown_until TEXT,
    total_success INTEGER NOT NULL DEFAULT 0,
    total_fail INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL UNIQUE,
    access_hash INTEGER,
    username TEXT,
    first_name TEXT NOT NULL DEFAULT '',
    last_name TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    is_bot INTEGER NOT NULL DEFAULT 0 CHECK(is_bot IN (0, 1)),
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK(is_deleted IN (0, 1)),
    last_seen TEXT,
    activity_quality TEXT NOT NULL DEFAULT 'UNKNOWN',
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    input_identifier TEXT NOT NULL,
    telegram_entity_id INTEGER,
    title TEXT,
    username TEXT,
    entity_type TEXT,
    scan_state TEXT NOT NULL DEFAULT 'NEW',
    last_scan_started TEXT,
    last_scan_finished TEXT,
    reported_member_count INTEGER,
    scanned_member_count INTEGER NOT NULL DEFAULT 0,
    scan_error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS source_members (
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_in_source TEXT,
    PRIMARY KEY (source_id, member_id)
);

CREATE TABLE IF NOT EXISTS targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    input_identifier TEXT NOT NULL,
    telegram_entity_id INTEGER,
    title TEXT,
    username TEXT,
    entity_type TEXT,
    validation_state TEXT NOT NULL DEFAULT 'NEW',
    last_validated TEXT,
    permission_state TEXT,
    validation_error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS target_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    snapshot_state TEXT NOT NULL DEFAULT 'NEW',
    captured_at TEXT,
    member_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS target_snapshot_members (
    snapshot_id INTEGER NOT NULL REFERENCES target_snapshots(id) ON DELETE CASCADE,
    member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    PRIMARY KEY (snapshot_id, member_id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    target_id INTEGER NOT NULL REFERENCES targets(id),
    target_snapshot_id INTEGER REFERENCES target_snapshots(id),
    filter_snapshot_json TEXT NOT NULL DEFAULT '{}',
    selected_accounts_json TEXT NOT NULL DEFAULT '[]',
    range_start INTEGER,
    range_end INTEGER,
    max_items INTEGER,
    state TEXT NOT NULL DEFAULT 'DRAFT',
    total INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS job_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    member_id INTEGER NOT NULL REFERENCES members(id),
    state TEXT NOT NULL DEFAULT 'CANDIDATE',
    priority INTEGER NOT NULL DEFAULT 100,
    lease_owner TEXT,
    lease_until TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    last_account_id INTEGER REFERENCES accounts(id),
    last_error_code TEXT,
    last_error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    UNIQUE(job_id, member_id)
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_member_id INTEGER NOT NULL REFERENCES job_members(id) ON DELETE CASCADE,
    account_id INTEGER REFERENCES accounts(id),
    attempt_no INTEGER NOT NULL,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    result TEXT,
    error_scope TEXT,
    error_code TEXT,
    error_message TEXT,
    UNIQUE(job_member_id, attempt_no)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_members_username ON members(username);
CREATE INDEX IF NOT EXISTS idx_source_members_member ON source_members(member_id);
CREATE INDEX IF NOT EXISTS idx_job_members_claim
    ON job_members(job_id, state, next_retry_at, priority, id);
CREATE INDEX IF NOT EXISTS idx_job_members_lease ON job_members(state, lease_until);
CREATE INDEX IF NOT EXISTS idx_attempts_job_member ON attempts(job_member_id, attempt_no);

CREATE INDEX IF NOT EXISTS idx_sources_entity ON sources(telegram_entity_id);
CREATE INDEX IF NOT EXISTS idx_targets_entity ON targets(telegram_entity_id);
CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state, id);
