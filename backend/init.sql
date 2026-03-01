-- ============================================================================
-- PBXMonitorX Database Schema
-- PostgreSQL 16+ required
-- Run: psql -U pbxmonitorx -d pbxmonitorx -f init.sql
-- ============================================================================

-- ── Extensions ──────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";      -- gen_random_uuid(), digest()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- Trigram index for text search

-- ── Enums ───────────────────────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE tls_policy_t AS ENUM ('verify', 'trust_self_signed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE user_role_t AS ENUM ('viewer', 'operator', 'admin');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE capability_t AS ENUM ('available', 'degraded', 'unavailable', 'untested');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE trunk_status_t AS ENUM ('registered', 'unregistered', 'error', 'unknown');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE sbc_status_t AS ENUM ('online', 'offline', 'unknown');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE alert_severity_t AS ENUM ('info', 'warning', 'critical');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE alert_state_t AS ENUM ('firing', 'acknowledged', 'resolved');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE audit_action_t AS ENUM (
        'user_login', 'user_login_failed', 'user_logout',
        'user_created', 'user_updated', 'user_deleted',
        'pbx_created', 'pbx_updated', 'pbx_deleted', 'pbx_test_connection',
        'backup_downloaded', 'backup_scheduled', 'backup_deleted',
        'backup_retention_applied', 'backup_triggered',
        'alert_rule_created', 'alert_rule_updated', 'alert_rule_deleted',
        'alert_acknowledged', 'alert_resolved',
        'config_changed', 'poll_completed', 'poll_failed',
        'session_expired', 'capability_probe'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── App Users ───────────────────────────────────────────────────────────────
-- These are users of PBXMonitorX itself (NOT 3CX users)
CREATE TABLE IF NOT EXISTS app_user (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username          VARCHAR(100) NOT NULL,
    email             VARCHAR(255),
    password_hash     VARCHAR(255) NOT NULL,     -- bcrypt, never plaintext
    role              user_role_t NOT NULL DEFAULT 'viewer',
    is_active         BOOLEAN NOT NULL DEFAULT true,
    failed_login_count INT NOT NULL DEFAULT 0,
    locked_until      TIMESTAMPTZ,               -- NULL = not locked
    last_login        TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_app_user_username UNIQUE (username),
    CONSTRAINT uq_app_user_email UNIQUE (email),
    CONSTRAINT ck_app_user_username_len CHECK (char_length(username) >= 3),
    CONSTRAINT ck_app_user_role CHECK (role IN ('viewer', 'operator', 'admin'))
);

-- ── PBX Instances ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pbx_instance (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name              VARCHAR(200) NOT NULL,
    base_url          VARCHAR(500) NOT NULL,      -- https://pbx.example.com:5001
    tls_policy        tls_policy_t NOT NULL DEFAULT 'verify',
    detected_version  VARCHAR(50),                -- e.g. "20.0.3.884"
    detected_build    VARCHAR(200),
    is_enabled        BOOLEAN NOT NULL DEFAULT true,
    poll_interval_s   INT NOT NULL DEFAULT 60,
    last_poll_at      TIMESTAMPTZ,
    last_success_at   TIMESTAMPTZ,
    last_error        TEXT,
    consecutive_failures INT NOT NULL DEFAULT 0,
    notes             TEXT,
    created_by        UUID REFERENCES app_user(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_pbx_instance_name UNIQUE (name),
    CONSTRAINT ck_pbx_poll_interval CHECK (poll_interval_s BETWEEN 30 AND 3600),
    CONSTRAINT ck_pbx_base_url CHECK (base_url ~ '^https://')
);

-- ── Encrypted Credentials ───────────────────────────────────────────────────
-- Password is AES-256-GCM encrypted. The encryption key is NEVER in this DB.
-- Fields: ciphertext (encrypted password), nonce (12-byte IV), tag (16-byte auth tag)
CREATE TABLE IF NOT EXISTS pbx_credential (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id            UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    username          VARCHAR(200) NOT NULL,       -- PBX admin username (stored plain — it's not secret)
    encrypted_password BYTEA NOT NULL,             -- AES-256-GCM ciphertext
    nonce             BYTEA NOT NULL,              -- 12-byte GCM nonce
    auth_tag          BYTEA NOT NULL,              -- 16-byte GCM authentication tag
    key_derivation    VARCHAR(50) NOT NULL DEFAULT 'direct',  -- 'direct' or 'pbkdf2'
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_pbx_credential UNIQUE (pbx_id),
    CONSTRAINT ck_nonce_len CHECK (octet_length(nonce) = 12),
    CONSTRAINT ck_tag_len CHECK (octet_length(auth_tag) = 16)
);

-- ── Capability Matrix (per PBX) ────────────────────────────────────────────
-- Stores what features are accessible on each PBX and how
CREATE TABLE IF NOT EXISTS pbx_capability (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id            UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    feature           VARCHAR(50) NOT NULL,        -- trunks, sbcs, license, backup_list, backup_download, backup_trigger
    status            capability_t NOT NULL DEFAULT 'untested',
    method            VARCHAR(50),                 -- api_json, web_call, html_scrape
    endpoint_path     VARCHAR(500),                -- discovered working endpoint
    response_shape    VARCHAR(100),                -- hint for parser: list, object, nested
    last_probed_at    TIMESTAMPTZ,
    notes             TEXT,

    CONSTRAINT uq_pbx_capability UNIQUE (pbx_id, feature)
);

-- ── Trunk State (current snapshot) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trunk_state (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id            UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    trunk_name        VARCHAR(300) NOT NULL,
    remote_id         VARCHAR(200),                -- 3CX internal trunk ID
    status            trunk_status_t NOT NULL DEFAULT 'unknown',
    last_error        TEXT,
    last_status_change TIMESTAMPTZ,
    inbound_enabled   BOOLEAN,
    outbound_enabled  BOOLEAN,
    provider          VARCHAR(200),
    extra_data        JSONB DEFAULT '{}',
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_trunk_state UNIQUE (pbx_id, trunk_name)
);

-- ── SBC State (current snapshot) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sbc_state (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id            UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    sbc_name          VARCHAR(300) NOT NULL,
    remote_id         VARCHAR(200),
    status            sbc_status_t NOT NULL DEFAULT 'unknown',
    last_seen         TIMESTAMPTZ,
    tunnel_status     VARCHAR(100),
    connection_info   JSONB DEFAULT '{}',
    extra_data        JSONB DEFAULT '{}',
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_sbc_state UNIQUE (pbx_id, sbc_name)
);

-- ── License State (current snapshot) ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS license_state (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id            UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    edition           VARCHAR(100),
    license_key_masked VARCHAR(20),               -- "ABCD...WXYZ" only first/last 4
    expiry_date       DATE,
    maintenance_expiry DATE,
    max_sim_calls     INT,
    is_valid          BOOLEAN,
    warnings          TEXT[] DEFAULT '{}',
    extra_data        JSONB DEFAULT '{}',
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_license_state UNIQUE (pbx_id)
);

-- ── Poll History (time-series) ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS poll_result (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id            UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    polled_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    poll_type         VARCHAR(30) NOT NULL,       -- full, trunks, sbcs, license
    success           BOOLEAN NOT NULL DEFAULT true,
    duration_ms       INT,
    trunk_data        JSONB,
    sbc_data          JSONB,
    license_data      JSONB,
    diff_summary      TEXT,                       -- human-readable change description
    error_message     TEXT
);
CREATE INDEX IF NOT EXISTS idx_poll_result_pbx_time ON poll_result (pbx_id, polled_at DESC);
-- Auto-cleanup: keep 90 days by default (implement via retention task)

-- ── Backups ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS backup_record (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id            UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    remote_backup_id  VARCHAR(300),               -- ID on the PBX
    filename          VARCHAR(500) NOT NULL,
    backup_type       VARCHAR(50),                -- full, config_only
    created_on_pbx    TIMESTAMPTZ,
    size_bytes        BIGINT,
    is_downloaded     BOOLEAN NOT NULL DEFAULT false,
    downloaded_at     TIMESTAMPTZ,
    storage_path      VARCHAR(1000),              -- local path on disk
    sha256_hash       VARCHAR(64),                -- hex digest
    is_encrypted      BOOLEAN NOT NULL DEFAULT false,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_backup_pbx_date ON backup_record (pbx_id, created_on_pbx DESC);

CREATE TABLE IF NOT EXISTS backup_schedule (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id            UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    cron_expr         VARCHAR(100) NOT NULL DEFAULT '0 2 * * *',  -- daily 2am
    is_enabled        BOOLEAN NOT NULL DEFAULT true,
    retain_count      INT,                        -- keep last N
    retain_days       INT,                        -- keep last X days
    encrypt_at_rest   BOOLEAN NOT NULL DEFAULT false,
    last_run_at       TIMESTAMPTZ,
    next_run_at       TIMESTAMPTZ,
    last_run_success  BOOLEAN,
    last_run_error    TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_backup_schedule UNIQUE (pbx_id)
);

-- ── Alerts ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alert_rule (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name              VARCHAR(200) NOT NULL,
    pbx_id            UUID REFERENCES pbx_instance(id) ON DELETE CASCADE,  -- NULL = all PBXes
    condition_type    VARCHAR(50) NOT NULL,        -- trunk_down, sbc_offline, license_expiring, backup_stale
    threshold_seconds INT,                         -- for time-based conditions
    threshold_days    INT,                         -- for date-based conditions
    severity          alert_severity_t NOT NULL DEFAULT 'warning',
    is_enabled        BOOLEAN NOT NULL DEFAULT true,
    notify_webhook    VARCHAR(500),
    notify_email      VARCHAR(255),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alert_event (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id           UUID NOT NULL REFERENCES alert_rule(id) ON DELETE CASCADE,
    pbx_id            UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    state             alert_state_t NOT NULL DEFAULT 'firing',
    severity          alert_severity_t NOT NULL,
    title             VARCHAR(500) NOT NULL,
    detail            TEXT,
    fingerprint       VARCHAR(200),               -- dedup key to avoid duplicates
    fired_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at   TIMESTAMPTZ,
    acknowledged_by   UUID REFERENCES app_user(id),
    resolved_at       TIMESTAMPTZ,
    extra_data        JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_alert_event_state ON alert_event (state, fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_event_fp ON alert_event (fingerprint) WHERE state = 'firing';

-- ── Audit Log (append-only) ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID REFERENCES app_user(id) ON DELETE SET NULL,
    username          VARCHAR(100),               -- denormalized — survives user deletion
    action            audit_action_t NOT NULL,
    target_type       VARCHAR(50),                -- pbx, backup, alert, user, system
    target_id         UUID,
    target_name       VARCHAR(300),
    detail            JSONB DEFAULT '{}',
    ip_address        INET,
    user_agent        VARCHAR(500),
    success           BOOLEAN NOT NULL DEFAULT true,
    error_message     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_time ON audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log (action);
CREATE INDEX IF NOT EXISTS idx_audit_log_target ON audit_log (target_type, target_id);

-- Full-text search on audit detail
CREATE INDEX IF NOT EXISTS idx_audit_log_detail_gin ON audit_log USING gin (detail jsonb_path_ops);

-- ── Row-level security (defense in depth) ───────────────────────────────────
-- Audit log is append-only: no UPDATE or DELETE via app
-- This is enforced at the application layer + this trigger
CREATE OR REPLACE FUNCTION prevent_audit_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit log records are immutable — updates and deletes are prohibited';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_no_update ON audit_log;
CREATE TRIGGER trg_audit_no_update
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();

-- ── Auto-update updated_at timestamps ───────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN SELECT unnest(ARRAY[
        'app_user', 'pbx_instance', 'pbx_credential',
        'backup_schedule', 'alert_rule'
    ])
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_updated_at ON %I; '
            'CREATE TRIGGER trg_updated_at BEFORE UPDATE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION update_updated_at();',
            tbl, tbl
        );
    END LOOP;
END $$;

-- ── Seed: default admin user ────────────────────────────────────────────────
-- Password: "admin" (bcrypt hash) — MUST be changed on first login
-- $2b$12$LJ3m4ys5Rn9JSICqGCOQxeWF10R.tCn7gJBd9B6HuKqWNm0mTviPi = "admin"
INSERT INTO app_user (username, email, password_hash, role)
VALUES ('admin', 'admin@localhost', '$2b$12$LJ3m4ys5Rn9JSICqGCOQxeWF10R.tCn7gJBd9B6HuKqWNm0mTviPi', 'admin')
ON CONFLICT (username) DO NOTHING;

-- ── Seed: default alert rules ───────────────────────────────────────────────
INSERT INTO alert_rule (name, condition_type, threshold_seconds, severity)
VALUES
    ('Trunk down > 60s',      'trunk_down',       60,  'critical'),
    ('SBC offline > 120s',    'sbc_offline',       120, 'critical'),
    ('License expiring < 30d','license_expiring',  NULL,'warning'),
    ('No backup > 24h',       'backup_stale',      86400,'warning')
ON CONFLICT DO NOTHING;

-- Set threshold_days for the license rule
UPDATE alert_rule SET threshold_days = 30 WHERE condition_type = 'license_expiring' AND threshold_days IS NULL;

-- ============================================================================
-- VERIFICATION: List all tables
-- ============================================================================
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
