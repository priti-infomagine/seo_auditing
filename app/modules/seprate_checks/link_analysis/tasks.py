"""Link analysis Celery background tasks."""
from uuid import UUID

from celery.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.core.logger import logger
from app.modules.seprate_checks.link_analysis.service import LinkAnalysisService
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async
from redis.asyncio import Redis


from typing import Optional


@celery_app.task(
    name="link_analysis.run_check",
    queue="crawler",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=0,
    acks_late=True,
    time_limit=settings.LINK_ANALYSIS_TIME_LIMIT,
    soft_time_limit=settings.LINK_ANALYSIS_SOFT_TIME_LIMIT,
    track_started=True,
)
def run_check(
    self,
    check_id: str,
    url: str,
    max_pages: Optional[int] = None,
) -> dict:
    """Celery task: run asynchronous link analysis crawl and evaluation."""
    logger.info(f"link_analysis.run_check: task started for check_id={check_id}, url={url}, max_pages={max_pages}")
    task_id = self.request.id

    def _report_progress(state, meta=None):
        if task_id:
            self.update_state(task_id=task_id, state=state, meta=meta)

    async def _run():
        redis_client = Redis.from_url(
            settings.REDIS_URL, decode_responses=True, socket_timeout=2
        )
        service = LinkAnalysisService(redis=redis_client)
        result = await service.run_check_async(
            check_id=UUID(check_id),
            url=url,
            max_pages=max_pages,
            update_state=_report_progress,
        )
        return result

    try:
        result = run_async(_run())
        logger.info(
            f"link_analysis.run_check: task finished for check_id={check_id}, "
            f"status={result.get('status') if isinstance(result, dict) else 'unknown'}"
        )
        return result
    except SoftTimeLimitExceeded:
        logger.warning(f"link_analysis.run_check: soft time limit exceeded for check_id={check_id}")
        raise
    except Exception as exc:
        logger.error(
            f"link_analysis.run_check: task failed for check_id={check_id}: {exc}",
            exc_info=True,
        )
        raise
