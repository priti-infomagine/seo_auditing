"""Celery tasks for the SERP rank check module.

The rank-check endpoint is now synchronous (the API handler calls
DataForSEO directly), so there is no ``run_serp_check`` task.

Queues:

- ``serp_preview`` — low concurrency preview rendering.
- ``serp_maintenance`` — stuck-job sweep.

Windows dev: run the ``serp_preview`` worker with ``--pool=threads``
(or gevent), not solo. Keep ``serp_preview`` at concurrency 1-2.
"""
from __future__ import annotations

from uuid import UUID

from app.core.logger import logger
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async

from .service import SerpRankCheckService


@celery_app.task(
    name="serp_rank_check.build_preview",
    queue="serp_preview",
    bind=True,
    acks_late=True,
    soft_time_limit=45,
    time_limit=60,
    track_started=True,
    max_retries=0,
)
def build_preview(self, check_id: str) -> dict:
    """Render and store the preview for a ranked check.

    A preview failure never fails the rank check: the result is
    kept and the job is marked ``done`` with
    ``preview_status='failed'``.
    """
    logger.info("serp_rank_check.build_preview: started id=%s", check_id)

    async def _run():
        return await SerpRankCheckService().build_preview_async(
            UUID(check_id)
        )

    try:
        result = run_async(_run())
        logger.info(
            "serp_rank_check.build_preview: COMPLETED id=%s preview_status=%s",
            check_id,
            result.get("preview_status"),
        )
        return result
    except Exception:
        logger.error(
            "serp_rank_check.build_preview: FAILED id=%s",
            check_id,
            exc_info=True,
        )
        raise


@celery_app.task(
    name="serp_rank_check.sweep_stuck_checks",
    queue="serp_maintenance",
    bind=True,
    acks_late=True,
    track_started=True,
)
def sweep_stuck_checks(self) -> dict:
    """Recover checks stuck in ``running`` for too long.

    Jobs with a stored raw response resume parsing; the rest are
    marked failed (STUCK).
    """
    logger.info("serp_rank_check.sweep_stuck_checks: started")

    async def _run():
        return await SerpRankCheckService().sweep_stuck_async()

    try:
        result = run_async(_run())
        logger.info(
            "serp_rank_check.sweep_stuck_checks: COMPLETED swept=%s "
            "resumed=%s failed=%s",
            result.get("swept"),
            result.get("resumed"),
            result.get("failed"),
        )
        return result
    except Exception:
        logger.error(
            "serp_rank_check.sweep_stuck_checks: FAILED", exc_info=True
        )
        raise
