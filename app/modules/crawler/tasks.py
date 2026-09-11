from datetime import datetime

from uuid import UUID, uuid4

from app.core.datetime_utils import utc_now
from app.core.database import async_session_factory
from app.core.logger import logger
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.services.crawl_orchestrator import CrawlOrchestrator
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async
from app.shared.utils.url_utils import get_domain


@celery_app.task(
    name="crawler.crawl_website",
    queue="crawler",
    bind=True,
    # Only auto-retry on transient infrastructure failures (DB / Redis
    # connectivity). Application-level errors — including the historical
    # "CrawlJob not found" — must NOT be retried because the row will not
    # appear between retries; instead the task self-heals by recreating
    # the row from the task arguments.
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
    time_limit=3600,
    soft_time_limit=3300,
    track_started=True,
)
def crawl_website(self, crawl_id: str, url: str, user_id: str, force: bool = False) -> dict:
    logger.info(
        f"crawler.crawl_website: task started for crawl_id={crawl_id}, url={url}, "
        f"user_id={user_id}"
    )

    async def _run():
        crawl_uuid = UUID(crawl_id)
        try:
            user_uuid = UUID(user_id)
        except (ValueError, TypeError):
            # Some enqueue paths use a placeholder user_id; we still need
            # *some* valid UUID for the FK on the recreated row.
            user_uuid = uuid4()
        async with async_session_factory() as db:
            job_repo = CrawlJobRepository(db)
            job = await job_repo.get_by_id(crawl_uuid)

            if job is None:
                # The CrawlJob row was missing. This can happen when the
                # DB was reset between POST /audit/analyze and the worker
                # picking up the task, or when a previous attempt inserted
                # the task but failed to commit the row.
                # We self-heal: create a fresh row from the task args
                # with safe defaults so the rest of the pipeline (and the
                # audit pipeline it eventually fires) can find it.
                logger.warning(
                    f"crawler.crawl_website: CrawlJob {crawl_id} not found; "
                    f"recreating from task args (url={url}, user_id={user_id})"
                )
                domain = get_domain(url) or ""
                job = CrawlJob(
                    id=crawl_uuid,
                    user_id=user_uuid,
                    url=url,
                    domain=domain,
                    status="queued",
                    max_pages=100,
                    max_depth=5,
                    crawl_config={
                        # Conservative defaults — the original POST
                        # likely specified tighter limits but we can't
                        # know them; the user will get a small crawl.
                        "max_depth": 5,
                        "max_pages": 100,
                        "concurrency": 5,
                        "request_timeout": 60,
                        "delay_ms": 0,
                        "follow_redirects": True,
                        "respect_robots": True,
                        "auto_analyze": True,
                    },
                    crawl_config_recovered=True,
                )
                await job_repo.create(job)
                await db.commit()
                # Re-fetch so any lazy/defaulted fields are populated
                job = await job_repo.get_by_id(crawl_uuid)

            if job.status not in ("queued", "crawling"):
                # Already completed / failed / cancelled — nothing to do.
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
                    await db.commit()

                    logger.info(
                        f"crawler.crawl_website: auto_analyze fired for "
                        f"audit_id={crawl_id}, force={force}"
                    )

                    # Fire the analysis pipeline asynchronously
                    celery_app.send_task(
                        "audit.run_analysis_pipeline",
                        args=[str(crawl_uuid)],
                        kwargs={"force": force},
                        queue="audit",
                    )
                    result["auto_analyze"] = True

                self.update_state(
                    state="SUCCESS",
                    meta={
                        "current": job.total_pages or 0,
                        "total": job.total_pages or 0,
                        "percent": 100,
                        "crawl_id": crawl_id,
                    },
                )
                logger.info(
                    f"crawler.crawl_website: task succeeded for crawl_id={crawl_id}, "
                    f"pages_crawled={result.get('pages_crawled')}"
                )
                return result
            except Exception as exc:
                await _mark_failed(db, crawl_uuid, str(exc))
                logger.error(
                    f"crawler.crawl_website: task failed for crawl_id={crawl_id}: {exc}",
                    exc_info=True,
                )
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
