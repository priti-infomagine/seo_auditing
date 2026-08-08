from uuid import UUID

from celery import shared_task
from sqlalchemy import select

from app.core.database import async_session_factory
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.services.crawl_orchestrator import CrawlOrchestrator
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async


@celery_app.task(
    name="crawler.crawl_website",
    queue="crawler",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    acks_late=True,
    time_limit=3600,
    soft_time_limit=3300,
)
def crawl_website(crawl_id: str, url: str, user_id: str) -> dict:
    async def _run():
        crawl_uuid = UUID(crawl_id)
        async with async_session_factory() as db:
            job_repo = CrawlJobRepository(db)
            job = await job_repo.get_by_id(crawl_uuid)
            if not job:
                raise ValueError(f"CrawlJob {crawl_id} not found")
            if job.status != "queued":
                return {"status": job.status, "crawl_id": crawl_id}

            try:
                orchestrator = CrawlOrchestrator(db, crawl_uuid)
                result = await orchestrator.run(
                    start_url=url,
                    max_depth=job.crawl_config.max_depth if job.crawl_config else 5,
                    max_pages=job.crawl_config.max_pages if job.crawl_config else 1000,
                    concurrency=job.crawl_config.concurrency if job.crawl_config else 10,
                    timeout_seconds=job.crawl_config.timeout_seconds if job.crawl_config else 30,
                    delay_ms=job.crawl_config.delay_ms if job.crawl_config else 0,
                    follow_redirects=job.crawl_config.follow_redirects if job.crawl_config else True,
                    respect_robots=job.crawl_config.respect_robots if job.crawl_config else True,
                    user_agent=job.crawl_config.user_agent if job.crawl_config else None,
                )
                return result
            except Exception as exc:
                await _mark_failed(db, crawl_uuid, str(exc))
                raise

    return run_async(_run())


async def _mark_failed(db, crawl_uuid: UUID, error_message: str) -> None:
    job_repo = CrawlJobRepository(db)
    job = await job_repo.get_by_id(crawl_uuid)
    if job and job.status not in ("completed", "failed", "cancelled"):
        from datetime import datetime, timezone
        job.status = "failed"
        job.error = error_message[:1024]
        job.completed_at = datetime.now(timezone.utc)
        await job_repo.update(job)
