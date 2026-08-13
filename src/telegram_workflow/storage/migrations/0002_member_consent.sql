ALTER TABLE members ADD COLUMN consent_state TEXT NOT NULL DEFAULT 'UNKNOWN'
    CHECK(consent_state IN ('UNKNOWN', 'OPTED_IN', 'OPTED_OUT'));
ALTER TABLE members ADD COLUMN consent_updated_at TEXT;
ALTER TABLE members ADD COLUMN notes TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_members_consent ON members(consent_state, id);
