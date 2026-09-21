"""
Lighthouse check service — orchestrates crawl → discover → pagespeed → persist.

Async flow (offloaded to a Celery worker via ``lighthouse.run_check``):

  1. Phase "crawl"   — Crawl the seed URL via CrawlOrchestrator (reuses the
                       crawler module: sitemap discovery + BFS link extraction).
  2. Phase "pagespeed" — Call Google PageSpeed Insights (Lighthouse) API per
                       discovered URL *concurrently* (asyncio.Semaphore) and
                       persist each LighthousePageResult row as it finishes,
                       reporting live progress to the Celery task state AND the
                       database so polling survives a worker crash.
  3. Phase "completed" — Finalize the tracking CrawlJob status + timestamps.

The tracking record is the existing ``CrawlJob`` row whose ``id`` *is* the
``check_id`` (mirrors the audit module where ``CrawlJob.id == audit_id``).
Progress phases are encoded in ``CrawlJob.crawl_config["phase"]`` so no schema
migration is required. CrawlJob.status is owned by this service through the
pagespeed phase (the orchestrator sets it to "completed" at end-of-crawl; we
re-open it to "crawling" to bracket the pagespeed phase).
"""
import asyncio
import time
from typing import Callable, Optional

from uuid import UUID, uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.datetime_utils import utc_now
from app.core.logger import logger
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.repositories.crawl_page_repository import CrawlPageRepository
from app.modules.crawler.services.crawl_orchestrator import CrawlOrchestrator
from app.modules.seprate_checks.google_lighthouse_check.model import Device, PageStatus
from app.modules.seprate_checks.google_lighthouse_check.pagespeed_client import (
    PagespeedClient,
)
from app.modules.seprate_checks.google_lighthouse_check.repository import (
    LighthousePageResultRepository,
)
from app.modules.seprate_checks.google_lighthouse_check.validation import (
    DEFAULT_CATEGORIES,
    normalize_categories,
    normalize_device,
    validate_max_pages,
    validate_url,
)
from app.shared.utils.url_utils import get_domain, normalize_url
from app.modules.crawler.services.url_ignore_service import UrlIgnoreService

# Map PageSpeed category names to DB scope names
_CATEGORY_TO_SCOPE = {
    "performance": "performance",
    "accessibility": "accessibility",
    "best-practices": "bestpractices",
    "seo": "seo",
}


class LighthouseCheckService:
    """Orchestrates the full Lighthouse check flow (crawl → pagespeed → persist).

    The ``check_id`` is the UUID of the ``CrawlJob`` created by ``prepare_check``.
    ``prepare_check`` + ``record_task_id`` run inline in the API request;
    ``run_check_async`` runs inside the Celery worker.
    """

    PAGESPEED_CONCURRENCY = 5
    PAGESPEED_TIMEOUT = 60  # seconds per API call

    def __init__(self):
        self.pagespeed_client = PagespeedClient()

    # ── Synchronous (in-request) setup ───────────────────────────────────

    async def prepare_check(
        self,
        db: AsyncSession,
        url: str,
        device: str,
        max_pages: int,
        category: Optional[list[str]],
        pagespeed_concurrency: int = PAGESPEED_CONCURRENCY,
    ) -> dict:
        """
        Create the tracking CrawlJob (``status="queued"``) and return the
        metadata the API layer needs to enqueue the Celery task.

        Does NOT enqueue anything — the caller sends the task and then calls
        ``record_task_id`` so the job records its Celery task id.

        Uses the request-injected ``db`` session (not a fresh
        ``async_session_factory``) so tests / FastAPI dependency overrides apply.
        """
        normalized_url = validate_url(url)
        device_norm = normalize_device(device)
        categories = normalize_categories(category) or list(DEFAULT_CATEGORIES)
        effective_max_pages = validate_max_pages(max_pages)

        check_id = uuid4()
        domain = get_domain(normalized_url) or "unknown"
        device_enum = Device(device_norm)

        crawl_config = {
            "max_pages": effective_max_pages,
            "max_depth": 3,
            "concurrency": 10,
            "request_timeout": 60,
            "delay_ms": 0,
            "follow_redirects": True,
            "respect_robots": True,
            "auto_analyze": False,
            "device": device_enum.value,
            "categories": categories,
            "pagespeed_concurrency": pagespeed_concurrency,
            "task_id": None,
            "phase": "queued",
        }

        job_repo = CrawlJobRepository(db)
        job = CrawlJob(
            id=check_id,
            user_id=uuid4(),  # no auth context on this endpoint; placeholder FK
            url=normalized_url,
            domain=domain,
            status="queued",
            max_pages=effective_max_pages,
            max_depth=3,
            crawl_config=crawl_config,
        )
        await job_repo.create(job)
        await db.commit()

        logger.info(
            f"LighthouseCheckService: prepared check_id={check_id}, domain={domain}, "
            f"device={device_enum.value}, max_pages={effective_max_pages}"
        )

        return {
            "check_id": str(check_id),
            "domain": domain,
            "url": normalized_url,
            "device": device_enum.value,
            "categories": categories,
            "max_pages": effective_max_pages,
            "pagespeed_concurrency": pagespeed_concurrency,
        }

    async def record_task_id(self, db: AsyncSession, check_id: str, task_id: str) -> None:
        """Persist the Celery task id against the CrawlJob tracking row."""
        try:
            check_uuid = UUID(check_id)
        except (ValueError, TypeError):
            logger.warning(f"record_task_id: invalid check_id={check_id!r}")
            return
        job_repo = CrawlJobRepository(db)
        job = await job_repo.get_by_id(check_uuid)
        if job is None:
            logger.warning(f"record_task_id: CrawlJob {check_id} not found")
            return
        # crawl_config is a plain JSONB column (not Mutable), so in-place dict
        # mutations are not flushed — reassign a fresh dict via the helper.
        self._mutate_crawl_config(
            job, {"task_id": task_id, "phase": "queued"}
        )
        await job_repo.update(job)
        await db.commit()

    @staticmethod
    def _mutate_crawl_config(job: CrawlJob, updates: dict) -> None:
        """Merge ``updates`` into ``job.crawl_config`` with a detected reassignment.

        ``CrawlJob.crawl_config`` maps to a plain PostgreSQL ``JSONB`` column
        (the model does not wrap it with ``Mutable.as_mutable``), so SQLAlchemy
        does NOT observe in-place dict mutations like ``job.crawl_config[k]=v``.
        Building a *new* dict and reassigning the attribute is the reliable way
        to get the change flushed/committed.
        """
        cfg = dict(job.crawl_config or {})
        cfg.update(updates)
        job.crawl_config = cfg

    # ── Background worker entry point ────────────────────────────────────

    async def run_check_async(
        self,
        check_id: UUID,
        url: str,
        device: str,
        max_pages: int,
        category: Optional[list[str]] = None,
        pagespeed_concurrency: int = PAGESPEED_CONCURRENCY,
        update_state: Optional[Callable[[str, dict], None]] = None,
    ) -> dict:
        """
        Execute the full check inside a Celery worker.

        Runs crawl (Phase 1) then parallel PageSpeed checks (Phase 2), persisting
        live progress to the DB so ``GET /lighthouse/status/{check_id}`` works
        even if the worker dies mid-run.
        """
        start = time.time()
        device_enum = Device(device.lower())
        categories = category or [
            "performance", "seo", "best-practices", "accessibility",
        ]
        domain = get_domain(url) or "unknown"

        # Phase 1: crawl the seed URL and discover internal page URLs.
        await self._set_check_phase(check_id, status="crawling", phase="crawl")
        try:
            crawled_urls = await self._crawl_and_collect(check_id, url, max_pages, categories)
        except Exception as exc:
            logger.error(
                f"LighthouseCheckService: crawl failed for check_id={check_id}: {exc}",
                exc_info=True,
            )
            await self.mark_check_failed(check_id, str(exc)[:1024])
            if update_state:
                update_state("FAILURE", {"check_id": str(check_id), "error": str(exc)[:255]})
            raise

        total = len(crawled_urls)
        logger.info(
            f"LighthouseCheckService: crawl done for check_id={check_id}, "
            f"discovered {total} URLs — starting pagespeed phase"
        )

        # Orchestrator sets status="completed" + completed_at at end-of-crawl.
        # Re-open to "crawling" with phase="pagespeed" so polling reflects that
        # the PageSpeed batch (the long pole) is now in progress.
        await self._set_check_phase(
            check_id, status="crawling", phase="pagespeed",
            extra={"pagespeed_total": total},
        )

        # Phase 2: parallel PageSpeed checks with live progress.
        succeeded = 0
        failed = 0

        async with async_session_factory() as db:
            results_repo = LighthousePageResultRepository(db)
            job_repo = CrawlJobRepository(db)

            semaphore = asyncio.Semaphore(pagespeed_concurrency)
            strategy = device_enum.value

            async def _check_one(target_url: str) -> tuple[str, Optional[dict], Optional[str]]:
                async with semaphore:
                    try:
                        raw = await self.pagespeed_client.fetch(
                            url=target_url,
                            strategy=strategy,
                            category=categories,
                        )
                        parsed = PagespeedClient.parse_result(raw, target_url, strategy)
                        parsed["status"] = "success"
                        return target_url, parsed, None
                    except httpx.HTTPStatusError as e:
                        logger.warning(
                            f"Pagespeed API error for {target_url}: "
                            f"status={e.response.status_code}"
                        )
                        return target_url, None, f"API error: {e.response.status_code}"
                    except Exception as e:
                        logger.error(
                            f"Pagespeed check failed for {target_url}: {e}", exc_info=True
                        )
                        return target_url, None, str(e)[:255]

            tasks = [asyncio.ensure_future(_check_one(u)) for u in crawled_urls]
            try:
                for coro in asyncio.as_completed(tasks):
                    done_url, parsed, err = await coro
                    if parsed:
                        succeeded += 1
                        await results_repo.insert(
                            check_id=check_id,
                            domain=domain,
                            url=parsed["url"],
                            device=device_enum,
                            status=PageStatus.SUCCESS,
                            reason=None,
                            performance_score=parsed.get("performance_score"),
                            seo_score=parsed.get("seo_score"),
                            fcp_ms=parsed.get("fcp_ms"),
                            lcp_ms=parsed.get("lcp_ms"),
                            tbt_ms=parsed.get("tbt_ms"),
                            cls=parsed.get("cls"),
                        )
                    else:
                        failed += 1
                        await results_repo.insert(
                            check_id=check_id,
                            domain=domain,
                            url=done_url,
                            device=device_enum,
                            status=PageStatus.FAILED,
                            reason=err,
                        )
                    # Commit each result so /status sees live progress.
                    await db.commit()
                    if update_state:
                        update_state(
                            "PROGRESS",
                            {
                                "current": succeeded + failed,
                                "total": total,
                                "succeeded": succeeded,
                                "failed": failed,
                                "phase": "pagespeed",
                                "check_id": str(check_id),
                            },
                        )
            except Exception as exc:
                for t in tasks:
                    if not t.done():
                        t.cancel()
                await db.rollback()
                await self.mark_check_failed(check_id, str(exc)[:1024])
                if update_state:
                    update_state("FAILURE", {"check_id": str(check_id), "error": str(exc)[:255]})
                raise

            # Finalize: mark the check completed.
            job = await job_repo.get_by_id(check_id)
            if job:
                job.status = "completed"
                job.completed_at = utc_now()
                job.duration_ms = int((time.time() - start) * 1000)
                self._mutate_crawl_config(
                    job,
                    {
                        "phase": "completed",
                        "pagespeed_succeeded": succeeded,
                        "pagespeed_failed": failed,
                    },
                )
                await job_repo.update(job)
                await db.commit()

            if update_state:
                update_state(
                    "SUCCESS",
                    {
                        "total": total,
                        "succeeded": succeeded,
                        "failed": failed,
                        "check_id": str(check_id),
                    },
                )

            logger.info(
                f"LighthouseCheckService: completed check_id={check_id}, "
                f"total={total}, succeeded={succeeded}, failed={failed}"
            )

            return {
                "check_id": str(check_id),
                "domain": domain,
                "device": device,
                "pagespeed_total": total,
                "pagespeed_succeeded": succeeded,
                "pagespeed_failed": failed,
                "status": "completed",
            }

    # ── Crawl + collect URLs (Phase 1) ───────────────────────────────────

    async def _crawl_and_collect(self, check_id: UUID, url: str, max_pages: int, categories: list[str]) -> list[str]:
        """
        Crawl the seed URL via CrawlOrchestrator using the *pre-existing*
        CrawlJob (``check_id``), then collect all successfully crawled internal
        HTML page URLs.

        CrawlOrchestrator:
          - Phase A: fetches robots.txt + sitemaps (SiteDiscoveryService),
            extracts page URLs listed in sitemaps
          - Phase B: BFS traversal of internal <a> links up to max_depth hops
          - Persists every crawled URL into the crawl_pages table

        After the crawl, CrawlPageRepository.get_by_audit_id(check_id)
        returns all discovered+visited pages. We filter to successful HTML
        pages (is_success=True, 200 <= status_code < 400).

        URLs matching any Lighthouse category-specific ignore pattern are
        excluded from the returned list and logged as skip records.
        """
        # Determine which scopes to check (intersection of requested categories and known scopes)
        lighthouse_scopes = [
            _CATEGORY_TO_SCOPE[c]
            for c in categories
            if c in _CATEGORY_TO_SCOPE
        ]

        # Load category-specific ignore patterns
        ignore_service = UrlIgnoreService(db=None)
        async with async_session_factory() as db:
            if lighthouse_scopes:
                await ignore_service.load_patterns(db, scopes=lighthouse_scopes)

            orchestrator = CrawlOrchestrator(db, check_id)
            await orchestrator.run(
                start_url=url,
                max_pages=max_pages,
                max_depth=3,
            )

            page_repo = CrawlPageRepository(db)
            pages = await page_repo.get_by_audit_id(check_id)

            seen: set[str] = set()
            valid_urls: list[str] = []
            for page in pages:
                if not page.is_success:
                    continue
                if page.status_code is None or not (200 <= page.status_code < 400):
                    continue
                norm = page.normalized_url or page.url
                if not norm:
                    continue
                if norm in seen:
                    continue

                # Check category-specific ignore patterns
                if ignore_service and lighthouse_scopes:
                    is_ignored, reason, scope = ignore_service.check_url(norm, None, all_loaded=True)
                    if is_ignored:
                        await ignore_service.log_skip(
                            db,
                            check_id,
                            norm,
                            norm,
                            reason,
                            scope,
                        )
                        continue

                seen.add(norm)
                valid_urls.append(norm)

            seed_norm = normalize_url(url)
            if seed_norm in valid_urls:
                valid_urls.remove(seed_norm)
                valid_urls.insert(0, seed_norm)

            return valid_urls

    # ── Phase/status helpers ─────────────────────────────────────────────

    async def _set_check_phase(
        self,
        check_id: UUID,
        status: Optional[str] = None,
        phase: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> None:
        """Update the CrawlJob status + ``crawl_config['phase']`` for a running check.

        ``extra`` is merged into ``crawl_config`` (e.g. ``pagespeed_total``).
        """
        async with async_session_factory() as db:
            job_repo = CrawlJobRepository(db)
            job = await job_repo.get_by_id(check_id)
            if job is None:
                logger.warning(f"_set_check_phase: CrawlJob {check_id} not found")
                return
            if status:
                job.status = status
            extra = dict(extra) if extra else {}
            if phase:
                extra["phase"] = phase
            if extra:
                self._mutate_crawl_config(job, extra)
            await job_repo.update(job)
            await db.commit()

    async def mark_check_failed(self, check_id: UUID, error_message: str) -> None:
        """Mark a check as failed (terminal)."""
        async with async_session_factory() as db:
            job_repo = CrawlJobRepository(db)
            job = await job_repo.get_by_id(check_id)
            if job is None:
                return
            if job.status not in ("completed", "failed", "cancelled"):
                job.status = "failed"
                job.error = error_message[:1024]
                job.completed_at = utc_now()
                self._mutate_crawl_config(job, {"phase": "failed"})
                await job_repo.update(job)
                await db.commit()
