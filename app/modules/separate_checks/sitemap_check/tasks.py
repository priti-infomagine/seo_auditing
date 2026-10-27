"""Sitemap Celery background tasks."""
from uuid import UUID

from app.core.logger import logger
from app.modules.separate_checks.sitemap_check.service import SitemapCheckService
from app.shared.exceptions import categorize_error
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
    task_id = self.request.id
    logger.info(
        "sitemap.run_check: task started for check_id=%s, url=%s, task_id=%s",
        check_id,
        url,
        task_id,
    )

    def _report_progress(state, meta=None):
        if task_id:
            self.update_state(task_id=task_id, state=state, meta=meta)

    async def _run():
        service = SitemapCheckService()
        result = await service.run_check_async(
            check_id=UUID(check_id),
            url=url,
            update_state=_report_progress,
        )
        return result

    try:
        result = run_async(_run())
        logger.info(
            "sitemap.run_check: task finished for check_id=%s, "
            "status=%s",
            check_id,
            result.get("status") if isinstance(result, dict) else "unknown",
        )
        return result
    except Exception as exc:
        error_code, user_message = categorize_error(exc)
        logger.error(
            "sitemap.run_check: task failed for check_id=%s "
            "(error_code=%s): %s",
            check_id,
            error_code,
            exc,
            exc_info=True,
        )
        raise
