"""
Celery tasks for the Google Lighthouse / PageSpeed check.

Enqueued by ``POST /api/v1/lighthouse/check`` and consumed by a worker
subscribed to the ``lighthouse`` queue:

    celery -A app.shared.tasks worker -l info -q lighthouse,crawler,audit,email

The task delegates to ``LighthouseCheckService.run_check_async`` which:
  1. crawls the seed URL (reusing CrawlOrchestrator) → discovers page URLs
  2. runs the PageSpeed Insights (Lighthouse) API concurrently per URL
  3. persists each LighthousePageResult row as it completes (live progress)
  4. finalizes the tracking CrawlJob(check_id) status

Progress is reported BOTH ways:
  - Celery ``self.update_state(PROGRESS, {...})``  → for GET /lighthouse/task/{task_id}
  - DB row deltas (CrawlJob.crawl_config + lighthouse_page_results counts) →
    for GET /lighthouse/status/{check_id}, which survives worker death.
"""
from uuid import UUID

from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async
from app.modules.seprate_checks.google_lighthouse_check.services import (
    LighthouseCheckService,
)


@celery_app.task(
    name="lighthouse.run_check",
    queue="lighthouse",
    bind=True,
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
    category: list | None = None,
    pagespeed_concurrency: int = 5,
):
    """
    Background task: crawl → parallel PageSpeed → persist results.

    Args mirror ``LighthouseCheckService.run_check_async``. ``self`` (bound
    task) supplies ``update_state`` for progress reporting.
    """
    async def _run() -> dict:
        service = LighthouseCheckService()
        return await service.run_check_async(
            check_id=UUID(check_id),
            url=url,
            device=device,
            max_pages=max_pages,
            category=category,
            pagespeed_concurrency=pagespeed_concurrency,
            update_state=self.update_state,
        )

    return run_async(_run())
