"""
Lighthouse (Google PageSpeed Insights) Celery tasks.

Tasks:
  - lighthouse.run_check: Crawl a seed URL, run PageSpeed Insights (Lighthouse)
    concurrently per discovered page, and persist results.

The worker entry point is ``lighthouse.run_check``, enqueued on the
``lighthouse`` queue by POST /lighthouse/check (see
``app.modules.seprate_checks.google_lighthouse_check.router``).

Design:
  - ``bind=True`` gives us ``self.update_state`` for live progress reporting
    (PROGRESS / SUCCESS / FAILURE states) back to the caller.
  - The heavy lifting lives in ``LighthouseCheckService.run_check_async``;
    this task is a thin synchronous wrapper that runs it on the worker's
    persistent event loop via ``run_async``.
  - ``check_id`` travels as a string over the wire (it is ``str(CrawlJob.id)``
    when enqueued) and is coerced to ``UUID`` here.
"""
from typing import Optional
from uuid import UUID

from app.core.logger import logger
from app.modules.seprate_checks.google_lighthouse_check.services import (
    LighthouseCheckService,
)
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async


@celery_app.task(
    name="lighthouse.run_check",
    queue="crawler",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
    time_limit=3600,
    soft_time_limit=3300,
    track_started=True,
)
def run_check(
    self,
    check_id: str,
    url: str,
    device: str,
    max_pages: int,
    category: Optional[list[str]] = None,
    pagespeed_concurrency: int = LighthouseCheckService.PAGESPEED_CONCURRENCY,
) -> dict:
    """
    Celery task: run a full Lighthouse/PageSpeed check for a tracking CrawlJob.

    Wraps ``LighthouseCheckService.run_check_async``, feeding it
    ``self.update_state`` so the worker can report PROGRESS state with
    per-page success/failure counts and the current phase.

    Args:
        check_id: UUID string of the CrawlJob (``CrawlJob.id``).  Created
            by ``LighthouseCheckService.prepare_check`` in the API request.
        url: The seed URL to crawl + check.
        device: Device strategy ("mobile" or "desktop").
        max_pages: Maximum number of pages to crawl.
        category: Optional list of Lighthouse categories
            (performance, seo, best-practices, accessibility).
            Defaults to all four when None.
        pagespeed_concurrency: Max concurrent PageSpeed API calls.

    Returns:
        Summary dict from ``LighthouseCheckService.run_check_async``.
    """
    logger.info(
        f"lighthouse.run_check: task started for check_id={check_id}, "
        f"url={url}, device={device}, max_pages={max_pages}"
    )

    async def _run():
        service = LighthouseCheckService()
        result = await service.run_check_async(
            check_id=UUID(check_id),
            url=url,
            device=device,
            max_pages=max_pages,
            category=category,
            pagespeed_concurrency=pagespeed_concurrency,
            update_state=self.update_state,
        )
        return result

    try:
        result = run_async(_run())
        logger.info(
            f"lighthouse.run_check: task finished for check_id={check_id}, "
            f"status={result.get('status') if isinstance(result, dict) else 'unknown'}"
        )
        return result
    except Exception as exc:
        logger.error(
            f"lighthouse.run_check: task failed for check_id={check_id}: {exc}",
            exc_info=True,
        )
        raise
