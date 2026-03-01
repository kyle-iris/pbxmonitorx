"""Celery worker configuration for polling and scheduled tasks."""

from celery import Celery
from celery.schedules import crontab

from src.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "pbxmonitorx",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Rate limiting: max 10 tasks per minute per worker
    worker_max_tasks_per_child=1000,
)

# ── Periodic Tasks (Celery Beat) ──────────────────

celery_app.conf.beat_schedule = {
    # Poll all enabled PBX instances every 60 seconds
    "poll-all-pbx": {
        "task": "src.worker.tasks.poll_all_instances",
        "schedule": 60.0,
    },
    # Check alert rules every 30 seconds
    "check-alerts": {
        "task": "src.worker.tasks.evaluate_alert_rules",
        "schedule": 30.0,
    },
    # Run backup retention cleanup daily at 3 AM
    "backup-retention": {
        "task": "src.worker.tasks.apply_backup_retention",
        "schedule": crontab(hour=3, minute=0),
    },
    # Re-probe PBX capabilities weekly
    "reprobe-capabilities": {
        "task": "src.worker.tasks.reprobe_all_capabilities",
        "schedule": crontab(hour=4, minute=0, day_of_week=0),  # Sunday 4 AM
    },
}
