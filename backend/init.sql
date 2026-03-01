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
        'session_expired', 'capability_probe',
        'sso_login', 'sso_login_failed', 'user_sso_login', 'user_sso_created',
        'user_deactivated', 'user_password_reset',
        'phone_numbers_synced', 'report_generated', 'backup_bulk_pull'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── App Users ───────────────────────────────────────────────────────────────
-- These are users of PBXMonitorX itself (NOT 3CX users)
CREATE TABLE IF NOT EXISTS app_user (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username          VARCHAR(100) NOT NULL,
    email             VARCHAR(255),
    password_hash     VARCHAR(255),               -- bcrypt, never plaintext; NULL for SSO-only users
    role              user_role_t NOT NULL DEFAULT 'viewer',
    auth_method       VARCHAR(20) NOT NULL DEFAULT 'local',  -- 'local' or 'azure_ad'
    azure_oid         VARCHAR(100),               -- Azure AD Object ID
    display_name      VARCHAR(200),               -- Full name from Azure AD
    last_sso_sync     TIMESTAMPTZ,               -- Last Azure AD sync timestamp
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

-- Azure OID must be unique when not null (partial unique index)
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_user_azure_oid
    ON app_user (azure_oid) WHERE azure_oid IS NOT NULL;

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

-- ── Trunk Phone Numbers (DIDs per trunk) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS trunk_phone_number (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id            UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    trunk_id          UUID REFERENCES trunk_state(id) ON DELETE SET NULL,
    trunk_name        VARCHAR(300) NOT NULL,
    phone_number      VARCHAR(50) NOT NULL,
    display_name      VARCHAR(200),
    number_type       VARCHAR(30) DEFAULT 'did',  -- did, tollfree, international, internal
    is_main_number    BOOLEAN DEFAULT false,
    inbound_enabled   BOOLEAN DEFAULT true,
    outbound_enabled  BOOLEAN DEFAULT true,
    description       TEXT,
    extra_data        JSONB DEFAULT '{}',
    last_seen_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_phone_pbx UNIQUE (pbx_id, phone_number)
);
CREATE INDEX IF NOT EXISTS idx_phone_pbx ON trunk_phone_number (pbx_id);
CREATE INDEX IF NOT EXISTS idx_phone_trunk ON trunk_phone_number (trunk_name);
CREATE INDEX IF NOT EXISTS idx_phone_number ON trunk_phone_number (phone_number);

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
        'backup_schedule', 'alert_rule', 'trunk_phone_number'
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

-- ── Migration helpers for existing databases ────────────────────────────────
-- These ALTER statements are idempotent so the script can be re-run safely.

-- SSO fields on app_user (for databases created before SSO support)
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS auth_method VARCHAR(20) NOT NULL DEFAULT 'local';
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS azure_oid VARCHAR(100);
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS display_name VARCHAR(200);
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS last_sso_sync TIMESTAMPTZ;

-- Make password_hash nullable for SSO-only users (for databases created before SSO)
ALTER TABLE app_user ALTER COLUMN password_hash DROP NOT NULL;

-- New audit actions (for databases where the enum was created before these values)
ALTER TYPE audit_action_t ADD VALUE IF NOT EXISTS 'sso_login';
ALTER TYPE audit_action_t ADD VALUE IF NOT EXISTS 'sso_login_failed';
ALTER TYPE audit_action_t ADD VALUE IF NOT EXISTS 'user_sso_login';
ALTER TYPE audit_action_t ADD VALUE IF NOT EXISTS 'user_sso_created';
ALTER TYPE audit_action_t ADD VALUE IF NOT EXISTS 'user_deactivated';
ALTER TYPE audit_action_t ADD VALUE IF NOT EXISTS 'user_password_reset';
ALTER TYPE audit_action_t ADD VALUE IF NOT EXISTS 'phone_numbers_synced';
ALTER TYPE audit_action_t ADD VALUE IF NOT EXISTS 'report_generated';
ALTER TYPE audit_action_t ADD VALUE IF NOT EXISTS 'backup_bulk_pull';

-- New audit actions for settings & notifications
ALTER TYPE audit_action_t ADD VALUE IF NOT EXISTS 'settings_updated';
ALTER TYPE audit_action_t ADD VALUE IF NOT EXISTS 'notification_sent';
ALTER TYPE audit_action_t ADD VALUE IF NOT EXISTS 'notification_channel_created';
ALTER TYPE audit_action_t ADD VALUE IF NOT EXISTS 'notification_channel_updated';
ALTER TYPE audit_action_t ADD VALUE IF NOT EXISTS 'notification_channel_deleted';

-- ── System Settings (key-value store) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_setting (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL DEFAULT '{}',
    category VARCHAR(50) NOT NULL DEFAULT 'general',  -- general, branding, notifications, backup, integrations
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by UUID REFERENCES app_user(id) ON DELETE SET NULL
);

-- ── Notification Channels ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notification_channel (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    channel_type VARCHAR(50) NOT NULL,  -- 'email', 'webhook', 'halopsa'
    config JSONB NOT NULL DEFAULT '{}',  -- {smtp_host, smtp_port, smtp_user, smtp_pass_encrypted, from_addr, to_addrs[]} for email; {url, headers, method} for webhook
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Notification Log ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notification_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID REFERENCES notification_channel(id) ON DELETE SET NULL,
    alert_event_id UUID REFERENCES alert_event(id) ON DELETE SET NULL,
    notification_type VARCHAR(50) NOT NULL,  -- 'alert_fired', 'alert_resolved', 'backup_failed', 'backup_success', 'sbc_offline', 'trunk_down'
    subject VARCHAR(500),
    body TEXT,
    recipient VARCHAR(500),
    success BOOLEAN NOT NULL DEFAULT true,
    error_message TEXT,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notification_log_time ON notification_log (sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_log_channel ON notification_log (channel_id);

-- ── Seed: default system settings ─────────────────────────────────────────
INSERT INTO system_setting (key, value, category, description) VALUES
    ('branding.company_name', '"PBXMonitorX"', 'branding', 'Company name shown in header and login'),
    ('branding.logo_url', '""', 'branding', 'URL or base64 data for custom logo'),
    ('branding.primary_color', '"#C8965A"', 'branding', 'Primary accent color (hex)'),
    ('branding.dark_mode', 'true', 'branding', 'Enable dark mode theme'),
    ('branding.favicon_url', '""', 'branding', 'Custom favicon URL'),
    ('backup.default_storage_path', '"/data/backups"', 'backup', 'Default local storage path for backups'),
    ('backup.storage_type', '"local"', 'backup', 'Storage backend: local, s3, sftp'),
    ('backup.s3_bucket', '""', 'backup', 'S3 bucket name for remote backup storage'),
    ('backup.s3_region', '""', 'backup', 'S3 region'),
    ('backup.s3_access_key', '""', 'backup', 'S3 access key'),
    ('backup.s3_secret_key_encrypted', '""', 'backup', 'S3 secret key (encrypted)'),
    ('backup.sftp_host', '""', 'backup', 'SFTP host for remote backup storage'),
    ('backup.sftp_port', '22', 'backup', 'SFTP port'),
    ('backup.sftp_user', '""', 'backup', 'SFTP username'),
    ('backup.sftp_path', '""', 'backup', 'Remote path on SFTP server'),
    ('backup.default_retain_count', '10', 'backup', 'Default number of backups to retain per PBX'),
    ('backup.default_retain_days', '30', 'backup', 'Default days to retain backups'),
    ('backup.default_encrypt_at_rest', 'false', 'backup', 'Encrypt backups at rest by default'),
    ('notifications.enabled', 'false', 'notifications', 'Enable notification system'),
    ('notifications.alert_on_trunk_down', 'true', 'notifications', 'Notify when trunk goes down'),
    ('notifications.alert_on_sbc_offline', 'true', 'notifications', 'Notify when SBC goes offline'),
    ('notifications.alert_on_backup_fail', 'true', 'notifications', 'Notify when backup fails'),
    ('notifications.alert_on_backup_success', 'false', 'notifications', 'Notify on successful backup'),
    ('notifications.alert_on_license_expiring', 'true', 'notifications', 'Notify when license is expiring'),
    ('notifications.alert_on_pbx_unreachable', 'true', 'notifications', 'Notify when PBX is unreachable'),
    ('integrations.halopsa_enabled', 'false', 'integrations', 'Enable HaloPSA integration'),
    ('integrations.halopsa_api_url', '""', 'integrations', 'HaloPSA API base URL'),
    ('integrations.halopsa_client_id', '""', 'integrations', 'HaloPSA OAuth client ID'),
    ('integrations.halopsa_client_secret_encrypted', '""', 'integrations', 'HaloPSA OAuth client secret (encrypted)'),
    ('integrations.halopsa_ticket_type_id', '0', 'integrations', 'Default ticket type ID in HaloPSA'),
    ('integrations.halopsa_agent_id', '0', 'integrations', 'Default agent/team ID in HaloPSA')
ON CONFLICT (key) DO NOTHING;

-- ============================================================================
-- VERIFICATION: List all tables
-- ============================================================================
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
