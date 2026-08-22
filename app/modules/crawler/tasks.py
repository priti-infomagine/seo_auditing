from datetime import datetime

from uuid import UUID

from app.core.datetime_utils import utc_now
from app.core.database import async_session_factory
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.services.crawl_orchestrator import CrawlOrchestrator
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async


@celery_app.task(
    name="crawler.crawl_website",
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
def crawl_website(self, crawl_id: str, url: str, user_id: str) -> dict:
    async def _run():
        crawl_uuid = UUID(crawl_id)
        async with async_session_factory() as db:
            job_repo = CrawlJobRepository(db)
            job = await job_repo.get_by_id(crawl_uuid)
            if not job:
                raise ValueError(f"CrawlJob {crawl_id} not found")
            if job.status != "queued":
                return {"status": job.status, "crawl_id": crawl_id}

            def _progress_callback(current_page: int, total_pages: int | None):
                total = total_pages or 0
                percent = min(100, int((current_page / total) * 100)) if total else 0
                self.update_state(
                    state="PROGRESS",
                    meta={
                        "current": current_page,
                        "total": total,
                        "percent": percent,
                        "crawl_id": crawl_id,
                    },
                )

            try:
                cfg = job.crawl_config or {}
                orchestrator = CrawlOrchestrator(db, crawl_uuid)
                result = await orchestrator.run(
                    start_url=url,
                    max_depth=cfg.get("max_depth", 5),
                    max_pages=cfg.get("max_pages", 1000),
                    concurrency=cfg.get("concurrency", 10),
                    timeout_seconds=cfg.get("request_timeout", 30),
                    delay_ms=cfg.get("delay_ms", 0),
                    follow_redirects=cfg.get("follow_redirects", True),
                    respect_robots=cfg.get("respect_robots", True),
                    user_agent=cfg.get("user_agent"),
                    progress_callback=_progress_callback,
                )

                # Fire auto-analyze pipeline if requested
                if cfg.get("auto_analyze"):
                    from uuid import uuid4
                    project_id = job.project_id 
                    # Update project_id on the job if it was None
                    if not job.project_id:
                        job.project_id = project_id
                        await job_repo.update(job)
                    await db.commit()

                    # Fire the analysis pipeline asynchronously
                    celery_app.send_task(
                        "audit.run_analysis_pipeline",
                        args=[str(project_id), str(crawl_uuid)],
                        queue="audit",
                    )
                    result["auto_analyze"] = True
                    result["project_id"] = str(project_id)

                self.update_state(
                    state="SUCCESS",
                    meta={
                        "current": job.total_pages or 0,
                        "total": job.total_pages or 0,
                        "percent": 100,
                        "crawl_id": crawl_id,
                    },
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
        job.status = "failed"
        job.error = error_message[:1024]
        job.completed_at = utc_now()
        job.progress_percent = 100
        await job_repo.update(job)
