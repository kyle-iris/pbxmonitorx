"""Notification service — sends email and webhook notifications on alert events.

Supports:
- SMTP email delivery
- Webhook POST (for HaloPSA integration and custom webhooks)
- Notification logging and retry tracking
- Global enable/disable via system_setting
"""

import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import (
    SystemSetting, NotificationChannel, NotificationLog,
    AlertEvent, PbxInstance,
)

logger = logging.getLogger("pbxmonitorx.notifications")


async def get_setting(db: AsyncSession, key: str, default=None):
    """Get a system setting value by key."""
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting is None:
        return default
    return setting.value


async def get_settings_by_category(db: AsyncSession, category: str) -> dict:
    """Get all settings in a category as a dict."""
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.category == category)
    )
    settings = result.scalars().all()
    return {s.key: s.value for s in settings}


async def notify_alert_fired(db: AsyncSession, alert_event: AlertEvent, pbx: PbxInstance):
    """Send notifications for a newly fired alert."""
    # Check if notifications are enabled globally
    enabled = await get_setting(db, "notifications.enabled", False)
    if not enabled:
        return

    # Determine which notification types to check based on alert
    notify_key = _alert_to_setting_key(alert_event)
    if notify_key:
        should_notify = await get_setting(db, notify_key, True)
        if not should_notify:
            return

    # Get all enabled channels
    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.is_enabled == True)
    )
    channels = result.scalars().all()

    subject = f"[{alert_event.severity.upper()}] {alert_event.title}"
    body = _build_alert_body(alert_event, pbx, "fired")

    for channel in channels:
        await _send_via_channel(db, channel, subject, body, alert_event.id, "alert_fired")


async def notify_alert_resolved(db: AsyncSession, alert_event: AlertEvent, pbx: PbxInstance):
    """Send notifications when an alert is resolved."""
    enabled = await get_setting(db, "notifications.enabled", False)
    if not enabled:
        return

    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.is_enabled == True)
    )
    channels = result.scalars().all()

    subject = f"[RESOLVED] {alert_event.title}"
    body = _build_alert_body(alert_event, pbx, "resolved")

    for channel in channels:
        await _send_via_channel(db, channel, subject, body, alert_event.id, "alert_resolved")


async def notify_backup_event(db: AsyncSession, pbx: PbxInstance, event_type: str, detail: dict):
    """Notify on backup success or failure."""
    enabled = await get_setting(db, "notifications.enabled", False)
    if not enabled:
        return

    setting_key = f"notifications.alert_on_backup_{'fail' if event_type == 'backup_failed' else 'success'}"
    should = await get_setting(db, setting_key, event_type == "backup_failed")
    if not should:
        return

    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.is_enabled == True)
    )
    channels = result.scalars().all()

    if event_type == "backup_failed":
        subject = f"[BACKUP FAILED] {pbx.name}"
        body = f"Backup failed for PBX: {pbx.name}\n\nError: {detail.get('error', 'Unknown')}"
    else:
        subject = f"[BACKUP OK] {pbx.name}"
        body = f"Backup successful for PBX: {pbx.name}\n\nFile: {detail.get('filename', 'N/A')}\nSize: {detail.get('size_bytes', 0)} bytes"

    for channel in channels:
        await _send_via_channel(db, channel, subject, body, None, event_type)


async def _send_via_channel(
    db: AsyncSession, channel: NotificationChannel,
    subject: str, body: str, alert_event_id: Optional[UUID], notification_type: str
):
    """Route notification to the appropriate channel handler."""
    try:
        if channel.channel_type == "email":
            recipients = channel.config.get("to_addrs", [])
            for recipient in recipients:
                success, error = await _send_email(channel.config, subject, body, recipient)
                db.add(NotificationLog(
                    channel_id=channel.id, alert_event_id=alert_event_id,
                    notification_type=notification_type, subject=subject,
                    body=body, recipient=recipient,
                    success=success, error_message=error,
                ))
        elif channel.channel_type in ("webhook", "halopsa"):
            success, error = await _send_webhook(channel.config, subject, body, notification_type)
            db.add(NotificationLog(
                channel_id=channel.id, alert_event_id=alert_event_id,
                notification_type=notification_type, subject=subject,
                body=body, recipient=channel.config.get("url", ""),
                success=success, error_message=error,
            ))
        await db.flush()
    except Exception as e:
        logger.exception(f"Failed to send via channel {channel.name}")
        db.add(NotificationLog(
            channel_id=channel.id, alert_event_id=alert_event_id,
            notification_type=notification_type, subject=subject,
            body=body, recipient="error",
            success=False, error_message=str(e),
        ))
        await db.flush()


async def _send_email(config: dict, subject: str, body: str, recipient: str) -> tuple[bool, Optional[str]]:
    """Send an email via SMTP."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config.get("from_addr", "pbxmonitorx@localhost")
        msg["To"] = recipient
        msg.attach(MIMEText(body, "plain"))

        # Build HTML version
        html_body = f"""<html><body style="font-family: sans-serif; color: #333;">
        <h2 style="color: #C8965A;">{subject}</h2>
        <pre style="background: #f5f5f5; padding: 15px; border-radius: 5px;">{body}</pre>
        <hr><p style="color: #999; font-size: 12px;">Sent by PBXMonitorX</p>
        </body></html>"""
        msg.attach(MIMEText(html_body, "html"))

        smtp_host = config.get("smtp_host", "localhost")
        smtp_port = int(config.get("smtp_port", 587))
        smtp_user = config.get("smtp_user", "")
        smtp_pass = config.get("smtp_pass", "")
        use_tls = config.get("use_tls", True)

        if use_tls:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            server.starttls()
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)

        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)

        server.send_message(msg)
        server.quit()
        logger.info(f"Email sent to {recipient}: {subject}")
        return True, None

    except Exception as e:
        logger.error(f"Email send failed to {recipient}: {e}")
        return False, str(e)


async def _send_webhook(config: dict, subject: str, body: str, notification_type: str) -> tuple[bool, Optional[str]]:
    """Send a webhook POST notification."""
    try:
        url = config.get("url", "")
        if not url:
            return False, "No webhook URL configured"

        headers = config.get("headers", {})
        headers.setdefault("Content-Type", "application/json")

        payload = {
            "type": notification_type,
            "subject": subject,
            "body": body,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "PBXMonitorX",
        }

        # HaloPSA-specific payload transformation
        if config.get("is_halopsa"):
            payload = _transform_halopsa_payload(config, subject, body, notification_type)

        async with httpx.AsyncClient(timeout=15) as client:
            method = config.get("method", "POST").upper()
            resp = await client.request(method, url, json=payload, headers=headers)
            if resp.status_code < 300:
                logger.info(f"Webhook sent to {url}: {subject}")
                return True, None
            else:
                error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning(f"Webhook failed: {error}")
                return False, error

    except Exception as e:
        logger.error(f"Webhook send failed: {e}")
        return False, str(e)


def _transform_halopsa_payload(config: dict, subject: str, body: str, notification_type: str) -> dict:
    """Transform notification into HaloPSA ticket creation format."""
    return {
        "summary": subject,
        "details": body,
        "tickettype_id": config.get("ticket_type_id", 1),
        "agent_id": config.get("agent_id", 0),
        "priority_id": 3 if "critical" in subject.lower() else 2,
        "category_1": "PBX Monitoring",
        "category_2": notification_type,
    }


def _build_alert_body(alert_event: AlertEvent, pbx: PbxInstance, action: str) -> str:
    """Build notification body text for an alert."""
    lines = [
        f"Alert {action.upper()}: {alert_event.title}",
        f"",
        f"PBX: {pbx.name} ({pbx.base_url})",
        f"Severity: {alert_event.severity}",
        f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
    ]
    if alert_event.detail:
        lines.append(f"Detail: {alert_event.detail}")
    if action == "resolved" and alert_event.resolved_at:
        duration = alert_event.resolved_at - alert_event.fired_at
        lines.append(f"Duration: {duration}")
    return "\n".join(lines)


def _alert_to_setting_key(alert_event: AlertEvent) -> Optional[str]:
    """Map alert fingerprint prefix to notification setting key."""
    fp = alert_event.fingerprint or ""
    if fp.startswith("trunk_down"):
        return "notifications.alert_on_trunk_down"
    elif fp.startswith("sbc_offline"):
        return "notifications.alert_on_sbc_offline"
    elif fp.startswith("backup_stale"):
        return "notifications.alert_on_backup_fail"
    elif fp.startswith("license_expiring"):
        return "notifications.alert_on_license_expiring"
    return None


# ═══════════════════════════════════════════════════════════════════════════
# CHANNEL CRUD (used by settings API)
# ═══════════════════════════════════════════════════════════════════════════

async def list_channels(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(NotificationChannel).order_by(NotificationChannel.name))
    return [
        {
            "id": str(ch.id), "name": ch.name, "channel_type": ch.channel_type,
            "config": ch.config, "is_enabled": ch.is_enabled,
            "created_at": ch.created_at.isoformat() if ch.created_at else None,
        }
        for ch in result.scalars().all()
    ]


async def create_channel(db: AsyncSession, name: str, channel_type: str, config: dict, is_enabled: bool = True) -> dict:
    ch = NotificationChannel(name=name, channel_type=channel_type, config=config, is_enabled=is_enabled)
    db.add(ch)
    await db.flush()
    return {"id": str(ch.id), "name": ch.name, "channel_type": ch.channel_type}


async def update_channel(db: AsyncSession, channel_id: UUID, updates: dict) -> bool:
    from sqlalchemy import update
    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.id == channel_id)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        return False
    for k, v in updates.items():
        if hasattr(ch, k):
            setattr(ch, k, v)
    await db.flush()
    return True


async def delete_channel(db: AsyncSession, channel_id: UUID) -> bool:
    from sqlalchemy import delete as sa_delete
    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.id == channel_id)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        return False
    await db.delete(ch)
    await db.flush()
    return True


async def test_channel(db: AsyncSession, channel_id: UUID) -> dict:
    """Send a test notification through a channel."""
    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.id == channel_id)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        return {"success": False, "error": "Channel not found"}

    subject = "[TEST] PBXMonitorX Notification Test"
    body = "This is a test notification from PBXMonitorX.\n\nIf you received this, your notification channel is configured correctly."

    if ch.channel_type == "email":
        recipients = ch.config.get("to_addrs", [])
        if not recipients:
            return {"success": False, "error": "No recipients configured"}
        success, error = await _send_email(ch.config, subject, body, recipients[0])
        return {"success": success, "error": error}
    elif ch.channel_type in ("webhook", "halopsa"):
        success, error = await _send_webhook(ch.config, subject, body, "test")
        return {"success": success, "error": error}

    return {"success": False, "error": f"Unknown channel type: {ch.channel_type}"}


async def get_notification_history(db: AsyncSession, limit: int = 50, channel_id: UUID = None) -> list[dict]:
    """Get recent notification log entries."""
    q = select(NotificationLog).order_by(NotificationLog.sent_at.desc()).limit(limit)
    if channel_id:
        q = q.where(NotificationLog.channel_id == channel_id)
    result = await db.execute(q)
    return [
        {
            "id": str(n.id), "channel_id": str(n.channel_id) if n.channel_id else None,
            "notification_type": n.notification_type, "subject": n.subject,
            "recipient": n.recipient, "success": n.success,
            "error_message": n.error_message,
            "sent_at": n.sent_at.isoformat() if n.sent_at else None,
        }
        for n in result.scalars().all()
    ]
