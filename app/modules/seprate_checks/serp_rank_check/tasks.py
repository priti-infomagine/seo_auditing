"""Celery tasks for the SERP rank check module.

Queues:

- ``serp_io`` — high concurrency rank checks (provider calls).
- ``serp_preview`` — low concurrency preview rendering.
- ``serp_maintenance`` — stuck-job sweep and reference refresh.

Windows dev: run the ``serp_io`` worker with ``--pool=threads``
(or gevent), not solo. Keep ``serp_preview`` at concurrency 1-2.
"""
from __future__ import annotations

from uuid import UUID

from app.core.logger import logger
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async

from .exceptions import SerpProvider5xx, SerpProviderTimeout
from .service import SerpRankCheckService, classify_error


@celery_app.task(
    name="serp_rank_check.run_serp_check",
    queue="serp_io",
    bind=True,
    autoretry_for=(SerpProviderTimeout, SerpProvider5xx),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
    soft_time_limit=45,
    time_limit=60,
    track_started=True,
)
def run_serp_check(self, check_id: str) -> dict:
    """Run a rank check: call the provider, parse, persist, enqueue preview."""
    logger.info("serp_rank_check.run_serp_check: started id=%s", check_id)

    async def _run():
        return await SerpRankCheckService().run_check_async(UUID(check_id))

    try:
        result = run_async(_run())
        logger.info(
            "serp_rank_check.run_serp_check: COMPLETED id=%s status=%s",
            check_id,
            result.get("status"),
        )
        return result
    except Exception as exc:
        # Retryable errors (timeout / 5xx) are redelivered
        # by Celery's autoretry, so mark failed only on the
        # final attempt. Non-retryable errors (4xx, parse,
        # unexpected) are never retried, so fail immediately.
        # The service already persists non-retryable failures,
        # and mark_failed_if_pending is idempotent, making this
        # a safe no-op for those.
        retryable = isinstance(
            exc, (SerpProviderTimeout, SerpProvider5xx)
        )
        if not retryable or self.request.retries >= self.max_retries:
            try:
                error_code = classify_error(exc)
                run_async(
                    SerpRankCheckService().mark_failed_if_pending_async(
                        UUID(check_id), error_code
                    )
                )
            except Exception:
                logger.error(
                    "serp_rank_check.run_serp_check: "
                    "failed to mark check %s failed",
                    check_id,
                    exc_info=True,
                )
        raise


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
        return await SerpRankCheckService().build_preview_async(UUID(check_id))

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


@celery_app.task(
    name="serp_rank_check.refresh_reference_data",
    queue="serp_maintenance",
    bind=True,
    acks_late=True,
    track_started=True,
)
def refresh_reference_data(self) -> dict:
    """Refresh serp_locations and serp_languages from the provider."""
    logger.info("serp_rank_check.refresh_reference_data: started")

    async def _run():
        return await SerpRankCheckService().refresh_reference_data_async()

    try:
        result = run_async(_run())
        logger.info(
            "serp_rank_check.refresh_reference_data: COMPLETED "
            "locations=%s languages=%s",
            result.get("locations"),
            result.get("languages"),
        )
        return result
    except Exception:
        logger.error(
            "serp_rank_check.refresh_reference_data: FAILED", exc_info=True
        )
        raise
