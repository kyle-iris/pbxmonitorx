-- PBXMonitorX Database Schema
-- PostgreSQL 15+

-- ============================================================
-- ENUM TYPES
-- ============================================================

CREATE TYPE pbx_tls_policy AS ENUM ('strict', 'trust_self_signed');
CREATE TYPE user_role AS ENUM ('viewer', 'operator', 'admin');
CREATE TYPE capability_status AS ENUM ('available', 'degraded', 'unavailable', 'unknown');
CREATE TYPE trunk_status AS ENUM ('registered', 'unregistered', 'error', 'unknown');
CREATE TYPE sbc_status AS ENUM ('online', 'offline', 'unknown');
CREATE TYPE alert_severity AS ENUM ('info', 'warning', 'critical');
CREATE TYPE alert_state AS ENUM ('active', 'acknowledged', 'resolved');
CREATE TYPE audit_action AS ENUM (
    'user_login', 'user_logout', 'user_created', 'user_updated',
    'pbx_added', 'pbx_updated', 'pbx_removed', 'pbx_test_connection',
    'backup_downloaded', 'backup_scheduled', 'backup_retention_applied',
    'alert_rule_created', 'alert_rule_updated', 'alert_acknowledged',
    'config_change', 'poll_failure', 'session_expired'
);

-- ============================================================
-- USERS & AUTH
-- ============================================================

CREATE TABLE app_user (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(100) UNIQUE NOT NULL,
    email           VARCHAR(255) UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,  -- bcrypt
    role            user_role NOT NULL DEFAULT 'viewer',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    failed_logins   INT NOT NULL DEFAULT 0,
    locked_until    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- PBX INSTANCES
-- ============================================================

CREATE TABLE pbx_instance (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    base_url        VARCHAR(500) NOT NULL,  -- https://pbx.example.com
    tls_policy      pbx_tls_policy NOT NULL DEFAULT 'strict',
    version         VARCHAR(50),            -- detected: e.g. "20.0.1.2"
    build_info      VARCHAR(200),
    is_enabled       BOOLEAN NOT NULL DEFAULT true,
    poll_interval_s INT NOT NULL DEFAULT 60,
    last_seen       TIMESTAMPTZ,
    last_error      TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- SECRETS (encrypted credentials)
-- ============================================================

CREATE TABLE secret_ref (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id          UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    username        VARCHAR(200) NOT NULL,  -- stored in plaintext (it's the login username)
    encrypted_password BYTEA NOT NULL,      -- AES-256-GCM encrypted
    encryption_iv   BYTEA NOT NULL,         -- IV for AES-GCM
    encryption_tag  BYTEA NOT NULL,         -- Auth tag for AES-GCM
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(pbx_id)
);

-- ============================================================
-- CAPABILITY MATRIX (per PBX)
-- ============================================================

CREATE TABLE pbx_capability (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id          UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    feature         VARCHAR(50) NOT NULL,   -- trunks, sbcs, license, backup_list, backup_download, trigger_backup
    status          capability_status NOT NULL DEFAULT 'unknown',
    method          VARCHAR(50),            -- api, web_call, scraping
    endpoint        VARCHAR(500),           -- discovered endpoint path
    last_tested     TIMESTAMPTZ,
    notes           TEXT,
    UNIQUE(pbx_id, feature)
);

-- ============================================================
-- POLL RESULTS (time-series)
-- ============================================================

CREATE TABLE poll_result (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id          UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    polled_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    poll_type       VARCHAR(50) NOT NULL,   -- trunks, sbcs, license, full
    raw_data        JSONB,                  -- full response for debugging
    parsed_data     JSONB NOT NULL,         -- structured extracted data
    diff_summary    TEXT,                   -- human-readable changes since last poll
    success         BOOLEAN NOT NULL DEFAULT true,
    error_message   TEXT,
    duration_ms     INT
);

CREATE INDEX idx_poll_result_pbx_time ON poll_result(pbx_id, polled_at DESC);
CREATE INDEX idx_poll_result_type ON poll_result(poll_type, polled_at DESC);

-- ============================================================
-- TRUNK STATUS (latest snapshot, denormalized for fast queries)
-- ============================================================

CREATE TABLE trunk_state (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id          UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    trunk_name      VARCHAR(300) NOT NULL,
    trunk_id_remote VARCHAR(200),           -- ID from 3CX if available
    status          trunk_status NOT NULL DEFAULT 'unknown',
    last_error      TEXT,
    last_change     TIMESTAMPTZ,
    inbound_ok      BOOLEAN,
    outbound_ok     BOOLEAN,
    provider        VARCHAR(200),
    extra_data      JSONB,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(pbx_id, trunk_name)
);

-- ============================================================
-- SBC STATUS (latest snapshot)
-- ============================================================

CREATE TABLE sbc_state (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id          UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    sbc_name        VARCHAR(300) NOT NULL,
    sbc_id_remote   VARCHAR(200),
    status          sbc_status NOT NULL DEFAULT 'unknown',
    last_seen       TIMESTAMPTZ,
    tunnel_status   VARCHAR(100),
    connection_info JSONB,
    extra_data      JSONB,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(pbx_id, sbc_name)
);

-- ============================================================
-- LICENSE STATUS (latest snapshot)
-- ============================================================

CREATE TABLE license_state (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id          UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    edition         VARCHAR(100),           -- Standard, Pro, Enterprise
    license_key     VARCHAR(100),           -- masked/partial
    expiry_date     DATE,
    maintenance_expiry DATE,
    max_simultaneous_calls INT,
    is_valid        BOOLEAN,
    warnings        TEXT[],
    extra_data      JSONB,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(pbx_id)
);

-- ============================================================
-- BACKUPS
-- ============================================================

CREATE TABLE backup_record (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id          UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    remote_id       VARCHAR(300),           -- backup ID on PBX
    remote_name     VARCHAR(500),           -- filename on PBX
    created_at_remote TIMESTAMPTZ,          -- when PBX created it
    size_bytes      BIGINT,
    backup_type     VARCHAR(50),            -- full, config_only, etc.
    is_downloaded   BOOLEAN NOT NULL DEFAULT false,
    downloaded_at   TIMESTAMPTZ,
    storage_path    VARCHAR(1000),          -- local path where stored
    file_hash       VARCHAR(128),           -- SHA-256
    is_encrypted    BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_backup_pbx_date ON backup_record(pbx_id, created_at_remote DESC);

CREATE TABLE backup_schedule (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pbx_id          UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    cron_expression VARCHAR(100) NOT NULL,  -- e.g. "0 2 * * *" (daily 2am)
    is_enabled      BOOLEAN NOT NULL DEFAULT true,
    retention_count INT,                    -- keep last N backups
    retention_days  INT,                    -- keep backups from last X days
    encrypt_backups BOOLEAN NOT NULL DEFAULT false,
    last_run        TIMESTAMPTZ,
    next_run        TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(pbx_id)
);

-- ============================================================
-- ALERTS
-- ============================================================

CREATE TABLE alert_rule (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    pbx_id          UUID REFERENCES pbx_instance(id) ON DELETE CASCADE,  -- NULL = applies to all
    condition_type  VARCHAR(100) NOT NULL,   -- trunk_down, sbc_offline, license_expiring, backup_stale
    threshold_value INT NOT NULL,            -- seconds, days, hours depending on type
    severity        alert_severity NOT NULL DEFAULT 'warning',
    is_enabled      BOOLEAN NOT NULL DEFAULT true,
    notify_webhook  VARCHAR(500),
    notify_email    VARCHAR(255),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE alert_event (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id         UUID NOT NULL REFERENCES alert_rule(id) ON DELETE CASCADE,
    pbx_id          UUID NOT NULL REFERENCES pbx_instance(id) ON DELETE CASCADE,
    state           alert_state NOT NULL DEFAULT 'active',
    severity        alert_severity NOT NULL,
    title           VARCHAR(500) NOT NULL,
    detail          TEXT,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by UUID REFERENCES app_user(id),
    resolved_at     TIMESTAMPTZ,
    extra_data      JSONB
);

CREATE INDEX idx_alert_event_state ON alert_event(state, triggered_at DESC);

-- ============================================================
-- AUDIT LOG
-- ============================================================

CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES app_user(id),
    username        VARCHAR(100),           -- denormalized for history
    action          audit_action NOT NULL,
    target_type     VARCHAR(100),           -- pbx, backup, alert, user, system
    target_id       UUID,
    target_name     VARCHAR(300),
    detail          JSONB,
    ip_address      INET,
    user_agent      VARCHAR(500),
    success         BOOLEAN NOT NULL DEFAULT true,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_time ON audit_log(created_at DESC);
CREATE INDEX idx_audit_log_user ON audit_log(user_id, created_at DESC);
CREATE INDEX idx_audit_log_action ON audit_log(action, created_at DESC);
CREATE INDEX idx_audit_log_target ON audit_log(target_type, target_id);
