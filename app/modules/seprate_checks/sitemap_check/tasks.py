"""Sitemap Celery background tasks."""
from uuid import UUID

from app.core.logger import logger
from app.modules.seprate_checks.sitemap_check.service import SitemapCheckService
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async


@celery_app.task(
    name="sitemap.run_check",
    queue="crawler",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=2,
    acks_late=True,
    time_limit=600,
    soft_time_limit=540,
    track_started=True,
)
def run_check(
    self,
    check_id: str,
    url: str,
) -> dict:
    """Celery task: run asynchronous sitemap discovery and evaluation."""
    logger.info(f"sitemap.run_check: task started for check_id={check_id}, url={url}")

    async def _run():
        service = SitemapCheckService()
        result = await service.run_check_async(
            check_id=UUID(check_id),
            url=url,
            update_state=lambda state, meta=None: self.update_state(
                state=state, meta=meta
            ),
        )
        return result

    try:
        result = run_async(_run())
        logger.info(
            f"sitemap.run_check: task finished for check_id={check_id}, "
            f"status={result.get('status') if isinstance(result, dict) else 'unknown'}"
        )
        return result
    except Exception as exc:
        logger.error(
            f"sitemap.run_check: task failed for check_id={check_id}: {exc}",
            exc_info=True,
        )
        raise
