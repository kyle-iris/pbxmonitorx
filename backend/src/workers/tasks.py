"""Celery tasks — bridge between Celery (sync) and our async services.

Each task creates its own async DB session and runs the corresponding
service function. This keeps the Celery worker simple and the business
logic in the service layer.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.workers.celery_app import celery_app
from src.core.config import get_settings

logger = logging.getLogger("pbxmonitorx.tasks")

# ═══════════════════════════════════════════════════════════════════════════
# Async helper — Celery tasks are sync, but our services are async
# ═══════════════════════════════════════════════════════════════════════════

def _get_session_factory():
    """Create a fresh async session factory for worker tasks."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_size=5, pool_pre_ping=True)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════════════
# POLLING TASK
# ═══════════════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, max_retries=0, soft_time_limit=120)
def poll_due_instances(self):
    """Find all PBXes that are due for polling and poll them.

    Beat runs this every 15s. Each PBX's own poll_interval_s (60, 300, 600, 3600)
    is checked inside poll_all_due_instances via the _is_poll_due() gating.
    """
    run_async(_poll_due())


async def _poll_due():
    factory = _get_session_factory()
    async with factory() as db:
        from src.services.polling_service import poll_all_due_instances
        results = await poll_all_due_instances(db)
        if results:
            logger.info(f"Poll cycle: {len(results)} PBX(es) polled")
        for r in results:
            if not r.get("success"):
                logger.warning(f"Poll failed: {r}")


@celery_app.task(bind=True, max_retries=1)
def poll_single(self, pbx_id: str):
    """Manually trigger a poll for a specific PBX instance."""
    run_async(_poll_single(pbx_id))


async def _poll_single(pbx_id: str):
    from uuid import UUID
    factory = _get_session_factory()
    async with factory() as db:
        from src.services.polling_service import poll_single_instance
        result = await poll_single_instance(db, UUID(pbx_id))
        logger.info(f"Manual poll {pbx_id}: {result}")


# ═══════════════════════════════════════════════════════════════════════════
# ALERT EVALUATION TASK
# ═══════════════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, max_retries=0, soft_time_limit=60)
def evaluate_alerts(self):
    """Evaluate all alert rules against current state."""
    run_async(_evaluate_alerts())


async def _evaluate_alerts():
    factory = _get_session_factory()
    async with factory() as db:
        from src.services.alert_service import evaluate_all_rules
        results = await evaluate_all_rules(db)
        for r in results:
            if r.get("fired") or r.get("resolved"):
                logger.info(f"Alerts: fired={r.get('fired',0)} resolved={r.get('resolved',0)}")


# ═══════════════════════════════════════════════════════════════════════════
# BACKUP SCHEDULE TASK
# ═══════════════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, max_retries=1, soft_time_limit=600)
def run_backup_schedules(self):
    """Check for due backup schedules and execute them."""
    run_async(_run_backups())


async def _run_backups():
    factory = _get_session_factory()
    async with factory() as db:
        from src.services.backup_service import run_due_backup_schedules
        results = await run_due_backup_schedules(db)
        for r in results:
            if r.get("success"):
                logger.info(f"Backup pulled: {r.get('filename')} ({r.get('size_bytes')} bytes)")
            else:
                logger.warning(f"Backup failed for PBX {r.get('pbx_id')}: {r.get('error')}")


@celery_app.task
def pull_backup_now(pbx_id: str):
    """Manually trigger a backup pull for a specific PBX."""
    run_async(_pull_backup(pbx_id))


async def _pull_backup(pbx_id: str):
    from uuid import UUID
    factory = _get_session_factory()
    async with factory() as db:
        from src.services.backup_service import pull_latest_backup
        result = await pull_latest_backup(db, UUID(pbx_id))
        logger.info(f"Manual backup pull {pbx_id}: {result}")


# ═══════════════════════════════════════════════════════════════════════════
# RETENTION TASK
# ═══════════════════════════════════════════════════════════════════════════

@celery_app.task(soft_time_limit=300)
def apply_backup_retention():
    """Apply retention policies — delete old backups."""
    run_async(_retention())


async def _retention():
    factory = _get_session_factory()
    async with factory() as db:
        from src.services.backup_service import apply_retention
        actions = await apply_retention(db)
        if actions:
            logger.info(f"Retention: deleted {len(actions)} backup(s)")


# ═══════════════════════════════════════════════════════════════════════════
# POLL HISTORY CLEANUP
# ═══════════════════════════════════════════════════════════════════════════

@celery_app.task(soft_time_limit=120)
def cleanup_poll_history():
    """Delete poll_result entries older than 90 days."""
    run_async(_cleanup())


async def _cleanup():
    factory = _get_session_factory()
    async with factory() as db:
        from src.models.models import PollResult
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        result = await db.execute(
            delete(PollResult).where(PollResult.polled_at < cutoff)
        )
        await db.commit()
        logger.info(f"Poll history cleanup: deleted rows older than 90 days")
