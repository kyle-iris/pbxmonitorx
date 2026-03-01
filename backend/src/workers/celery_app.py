"""Celery application — task queue + periodic beat schedule."""

from celery import Celery
from celery.schedules import crontab
from src.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "pbxmonitorx",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.workers.tasks"],
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
    worker_max_tasks_per_child=500,
    # Prevent piling up if workers are slow
    broker_transport_options={"visibility_timeout": 300},
)

# ═══════════════════════════════════════════════════════════════════════════
# PERIODIC BEAT SCHEDULE
#
# The polling engine runs every 15 seconds; each PBX has its own interval
# (1, 5, 10, or 60 min) tracked via last_poll_at in the DB. The beat just
# dispatches the "check which are due" task frequently.
# ═══════════════════════════════════════════════════════════════════════════

celery_app.conf.beat_schedule = {
    # Check for PBXes due for polling — runs frequently, actual poll is gated per-PBX
    "poll-due-instances": {
        "task": "src.workers.tasks.poll_due_instances",
        "schedule": 15.0,  # Every 15 seconds
    },

    # Evaluate alert rules against current state
    "evaluate-alerts": {
        "task": "src.workers.tasks.evaluate_alerts",
        "schedule": 30.0,  # Every 30 seconds
    },

    # Run any due backup schedules
    "run-backup-schedules": {
        "task": "src.workers.tasks.run_backup_schedules",
        "schedule": 60.0,  # Every minute, checks cron internally
    },

    # Retention cleanup — daily at 03:00 UTC
    "backup-retention": {
        "task": "src.workers.tasks.apply_backup_retention",
        "schedule": crontab(hour=3, minute=0),
    },

    # Poll history cleanup — daily at 04:00 UTC, keep 90 days
    "poll-history-cleanup": {
        "task": "src.workers.tasks.cleanup_poll_history",
        "schedule": crontab(hour=4, minute=0),
    },
}
