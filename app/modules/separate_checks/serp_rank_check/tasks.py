"""Celery tasks for the SERP rank check module.

The rank-check endpoint is now synchronous (the API handler calls
DataForSEO directly), so there is no ``run_serp_check`` task.

Queues:

- ``serp_maintenance`` — stuck-job sweep.
"""
from __future__ import annotations

from app.core.logger import logger
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async

from .service import SerpRankCheckService


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
