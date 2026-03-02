"""SQLAlchemy ORM models — mirrors init.sql schema exactly."""

import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Date, Enum, ForeignKey, Integer,
    LargeBinary, String, Text, BigInteger, ARRAY, Index,
    text, UniqueConstraint, CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET, ENUM as PG_ENUM
from sqlalchemy.orm import DeclarativeBase, relationship


tls_policy_enum = PG_ENUM(
    'verify', 'trust_self_signed',
    name='tls_policy_t', create_type=False,
)

user_role_enum = PG_ENUM(
    'viewer', 'operator', 'admin',
    name='user_role_t', create_type=False,
)

capability_enum = PG_ENUM(
    'available', 'degraded', 'unavailable', 'untested',
    name='capability_t', create_type=False,
)

trunk_status_enum = PG_ENUM(
    'registered', 'unregistered', 'error', 'unknown',
    name='trunk_status_t', create_type=False,
)

sbc_status_enum = PG_ENUM(
    'online', 'offline', 'unknown',
    name='sbc_status_t', create_type=False,
)

alert_severity_enum = PG_ENUM(
    'info', 'warning', 'critical',
    name='alert_severity_t', create_type=False,
)

alert_state_enum = PG_ENUM(
    'firing', 'acknowledged', 'resolved',
    name='alert_state_t', create_type=False,
)

audit_action_enum = PG_ENUM(
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
    'phone_numbers_synced', 'report_generated', 'backup_bulk_pull',
    'settings_updated', 'notification_sent',
    'notification_channel_created', 'notification_channel_updated',
    'notification_channel_deleted',
    name='audit_action_t', create_type=False,
)


class Base(DeclarativeBase):
    pass


class AppUser(Base):
    __tablename__ = "app_user"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True)
    password_hash = Column(String(255), nullable=True)       # NULL for SSO-only users
    role = Column(user_role_enum, nullable=False, default="viewer")
    auth_method = Column(String(20), nullable=False, default="local")  # 'local' or 'azure_ad'
    azure_oid = Column(String(100))                          # Azure AD Object ID
    display_name = Column(String(200))                       # Full name from Azure AD
    last_sso_sync = Column(DateTime(timezone=True))           # Last Azure AD sync timestamp
    is_active = Column(Boolean, nullable=False, default=True)
    failed_login_count = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True))
    last_login = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))

    __table_args__ = (
        Index(
            "idx_app_user_azure_oid",
            "azure_oid",
            unique=True,
            postgresql_where=text("azure_oid IS NOT NULL"),
        ),
    )


class PbxInstance(Base):
    __tablename__ = "pbx_instance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), unique=True, nullable=False)
    base_url = Column(String(500), nullable=False)
    tls_policy = Column(tls_policy_enum, nullable=False, default="verify")
    detected_version = Column(String(50))
    detected_build = Column(String(200))
    is_enabled = Column(Boolean, nullable=False, default=True)
    poll_interval_s = Column(Integer, nullable=False, default=60)
    last_poll_at = Column(DateTime(timezone=True))
    last_success_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    notes = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))

    credential = relationship("PbxCredential", back_populates="pbx", uselist=False, cascade="all, delete-orphan")
    capabilities = relationship("PbxCapability", back_populates="pbx", cascade="all, delete-orphan")


class PbxCredential(Base):
    __tablename__ = "pbx_credential"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pbx_id = Column(UUID(as_uuid=True), ForeignKey("pbx_instance.id", ondelete="CASCADE"), unique=True, nullable=False)
    username = Column(String(200), nullable=False)
    encrypted_password = Column(LargeBinary, nullable=False)
    nonce = Column(LargeBinary, nullable=False)
    auth_tag = Column(LargeBinary, nullable=False)
    key_derivation = Column(String(50), nullable=False, default="direct")
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))

    pbx = relationship("PbxInstance", back_populates="credential")


class PbxCapability(Base):
    __tablename__ = "pbx_capability"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pbx_id = Column(UUID(as_uuid=True), ForeignKey("pbx_instance.id", ondelete="CASCADE"), nullable=False)
    feature = Column(String(50), nullable=False)
    status = Column(capability_enum, nullable=False, default="untested")
    method = Column(String(50))
    endpoint_path = Column(String(500))
    response_shape = Column(String(100))
    last_probed_at = Column(DateTime(timezone=True))
    notes = Column(Text)

    pbx = relationship("PbxInstance", back_populates="capabilities")

    __table_args__ = (UniqueConstraint("pbx_id", "feature"),)


class TrunkState(Base):
    __tablename__ = "trunk_state"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pbx_id = Column(UUID(as_uuid=True), ForeignKey("pbx_instance.id", ondelete="CASCADE"), nullable=False)
    trunk_name = Column(String(300), nullable=False)
    remote_id = Column(String(200))
    status = Column(trunk_status_enum, nullable=False, default="unknown")
    last_error = Column(Text)
    last_status_change = Column(DateTime(timezone=True))
    inbound_enabled = Column(Boolean)
    outbound_enabled = Column(Boolean)
    provider = Column(String(200))
    extra_data = Column(JSONB, default={})
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))

    phone_numbers = relationship("TrunkPhoneNumber", back_populates="trunk", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("pbx_id", "trunk_name"),)


class TrunkPhoneNumber(Base):
    __tablename__ = "trunk_phone_number"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pbx_id = Column(UUID(as_uuid=True), ForeignKey("pbx_instance.id", ondelete="CASCADE"), nullable=False)
    trunk_id = Column(UUID(as_uuid=True), ForeignKey("trunk_state.id", ondelete="SET NULL"))
    trunk_name = Column(String(300), nullable=False)
    phone_number = Column(String(50), nullable=False)
    display_name = Column(String(200))
    number_type = Column(String(30), default="did")        # did, tollfree, international, internal
    is_main_number = Column(Boolean, default=False)
    inbound_enabled = Column(Boolean, default=True)
    outbound_enabled = Column(Boolean, default=True)
    description = Column(Text)
    extra_data = Column(JSONB, default={})
    last_seen_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))

    trunk = relationship("TrunkState", back_populates="phone_numbers")

    __table_args__ = (
        UniqueConstraint("pbx_id", "phone_number", name="uq_phone_pbx"),
        Index("idx_phone_pbx", "pbx_id"),
        Index("idx_phone_trunk", "trunk_name"),
        Index("idx_phone_number", "phone_number"),
    )


class SbcState(Base):
    __tablename__ = "sbc_state"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pbx_id = Column(UUID(as_uuid=True), ForeignKey("pbx_instance.id", ondelete="CASCADE"), nullable=False)
    sbc_name = Column(String(300), nullable=False)
    remote_id = Column(String(200))
    status = Column(sbc_status_enum, nullable=False, default="unknown")
    last_seen = Column(DateTime(timezone=True))
    tunnel_status = Column(String(100))
    connection_info = Column(JSONB, default={})
    extra_data = Column(JSONB, default={})
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))

    __table_args__ = (UniqueConstraint("pbx_id", "sbc_name"),)


class LicenseState(Base):
    __tablename__ = "license_state"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pbx_id = Column(UUID(as_uuid=True), ForeignKey("pbx_instance.id", ondelete="CASCADE"), unique=True, nullable=False)
    edition = Column(String(100))
    license_key_masked = Column(String(20))
    expiry_date = Column(Date)
    maintenance_expiry = Column(Date)
    max_sim_calls = Column(Integer)
    is_valid = Column(Boolean)
    warnings = Column(ARRAY(Text), default=[])
    extra_data = Column(JSONB, default={})
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))


class PollResult(Base):
    __tablename__ = "poll_result"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pbx_id = Column(UUID(as_uuid=True), ForeignKey("pbx_instance.id", ondelete="CASCADE"), nullable=False)
    polled_at = Column(DateTime(timezone=True), server_default=text("now()"))
    poll_type = Column(String(30), nullable=False)
    success = Column(Boolean, nullable=False, default=True)
    duration_ms = Column(Integer)
    trunk_data = Column(JSONB)
    sbc_data = Column(JSONB)
    license_data = Column(JSONB)
    diff_summary = Column(Text)
    error_message = Column(Text)


class BackupRecord(Base):
    __tablename__ = "backup_record"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pbx_id = Column(UUID(as_uuid=True), ForeignKey("pbx_instance.id", ondelete="CASCADE"), nullable=False)
    remote_backup_id = Column(String(300))
    filename = Column(String(500), nullable=False)
    backup_type = Column(String(50))
    created_on_pbx = Column(DateTime(timezone=True))
    size_bytes = Column(BigInteger)
    is_downloaded = Column(Boolean, nullable=False, default=False)
    downloaded_at = Column(DateTime(timezone=True))
    storage_path = Column(String(1000))
    sha256_hash = Column(String(64))
    is_encrypted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))


class BackupSchedule(Base):
    __tablename__ = "backup_schedule"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pbx_id = Column(UUID(as_uuid=True), ForeignKey("pbx_instance.id", ondelete="CASCADE"), unique=True, nullable=False)
    cron_expr = Column(String(100), nullable=False, default="0 2 * * *")
    is_enabled = Column(Boolean, nullable=False, default=True)
    retain_count = Column(Integer)
    retain_days = Column(Integer)
    encrypt_at_rest = Column(Boolean, nullable=False, default=False)
    last_run_at = Column(DateTime(timezone=True))
    next_run_at = Column(DateTime(timezone=True))
    last_run_success = Column(Boolean)
    last_run_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))


class AlertRule(Base):
    __tablename__ = "alert_rule"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    pbx_id = Column(UUID(as_uuid=True), ForeignKey("pbx_instance.id", ondelete="CASCADE"))
    condition_type = Column(String(50), nullable=False)
    threshold_seconds = Column(Integer)
    threshold_days = Column(Integer)
    severity = Column(alert_severity_enum, nullable=False, default="warning")
    is_enabled = Column(Boolean, nullable=False, default=True)
    notify_webhook = Column(String(500))
    notify_email = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))


class AlertEvent(Base):
    __tablename__ = "alert_event"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id = Column(UUID(as_uuid=True), ForeignKey("alert_rule.id", ondelete="CASCADE"), nullable=False)
    pbx_id = Column(UUID(as_uuid=True), ForeignKey("pbx_instance.id", ondelete="CASCADE"), nullable=False)
    state = Column(alert_state_enum, nullable=False, default="firing")
    severity = Column(alert_severity_enum, nullable=False)
    title = Column(String(500), nullable=False)
    detail = Column(Text)
    fingerprint = Column(String(200))
    fired_at = Column(DateTime(timezone=True), server_default=text("now()"))
    acknowledged_at = Column(DateTime(timezone=True))
    acknowledged_by = Column(UUID(as_uuid=True), ForeignKey("app_user.id"))
    resolved_at = Column(DateTime(timezone=True))
    extra_data = Column(JSONB, default={})


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"))
    username = Column(String(100))
    action = Column(audit_action_enum, nullable=False)
    target_type = Column(String(50))
    target_id = Column(UUID(as_uuid=True))
    target_name = Column(String(300))
    detail = Column(JSONB, default={})
    ip_address = Column(INET)
    user_agent = Column(String(500))
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))


class SystemSetting(Base):
    __tablename__ = "system_setting"

    key = Column(String(100), primary_key=True)
    value = Column(JSONB, nullable=False, default={})
    category = Column(String(50), nullable=False, default="general")
    description = Column(Text)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))
    updated_by = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"))


class NotificationChannel(Base):
    __tablename__ = "notification_channel"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    channel_type = Column(String(50), nullable=False)
    config = Column(JSONB, nullable=False, default={})
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("notification_channel.id", ondelete="SET NULL"))
    alert_event_id = Column(UUID(as_uuid=True), ForeignKey("alert_event.id", ondelete="SET NULL"))
    notification_type = Column(String(50), nullable=False)
    subject = Column(String(500))
    body = Column(Text)
    recipient = Column(String(500))
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text)
    sent_at = Column(DateTime(timezone=True), server_default=text("now()"))


class EventLog(Base):
    __tablename__ = "event_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    level = Column(String(20), nullable=False, default="info")
    source = Column(String(100), nullable=False)
    pbx_id = Column(UUID(as_uuid=True), ForeignKey("pbx_instance.id", ondelete="SET NULL"))
    pbx_name = Column(String(200))
    event_type = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    detail = Column(JSONB, default={})
    duration_ms = Column(Integer)
    error_trace = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
