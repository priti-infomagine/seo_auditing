"""
Lighthouse check service — orchestrates crawl → discover → pagespeed → persist.

Flow:
  1. Crawl the seed URL using CrawlOrchestrator (reuses the crawler module)
  2. Collect all crawled internal URLs via CrawlPageRepository
  3. Call Google PageSpeed Insights (Lighthouse) API per URL
  4. Persist results to lighthouse_page_results table

The crawler module (CrawlerService / CrawlOrchestrator) handles all crawling
logic — sitemap discovery, BFS link extraction, robots.txt. This service
merely drives it and then runs Lighthouse on the discovered URLs.
"""
import asyncio
from typing import Optional
from uuid import UUID, uuid4

import httpx

from app.core.database import async_session_factory
from app.core.logger import logger
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.models.crawl_pages import CrawlPage
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
from app.shared.utils.url_utils import get_domain, normalize_url


class LighthouseCheckService:
    """
    Orchestrates the full Lighthouse check flow:

    crawl seed URL → discover related URLs → run Pagespeed API → persist results
    """

    # PageSpeed API free tier: ~30000 QPD, but recommend <= 10 concurrent
    # to avoid rate-limiting (quota user errors).
    PAGESPEED_CONCURRENCY = 5
    PAGESPEED_TIMEOUT = 60  # seconds per API call

    def __init__(self):
        self.pagespeed_client = PagespeedClient()

    async def run_check(
        self,
        url: str,
        device: str = "mobile",
        max_pages: int = 20,
    ) -> dict:
        """
        Run a full Lighthouse check.

        Args:
            url: Seed URL to crawl.
            device: 'mobile' or 'desktop' Lighthouse strategy.
            max_pages: Cap on total pages to crawl and check.

        Returns:
            dict with: check_id, domain, device, urls_checked, results
        """
        check_id = uuid4()
        domain = get_domain(url) or "unknown"
        device_enum = Device(device.lower())

        # ── Phase 1: Crawl the seed URL and discover related URLs ──────
        crawled_urls = await self._crawl_and_collect(url, max_pages)

        logger.info(
            f"LighthouseCheckService: crawled {len(crawled_urls)} URLs for "
            f"check_id={check_id}, domain={domain}"
        )

        # If crawl yielded no URLs, still record the check with zero results
        if not crawled_urls:
            logger.warning(
                f"LighthouseCheckService: no valid URLs discovered for {url}"
            )

        # ── Phase 2: Run Pagespeed API checks concurrently ────────────
        results = await self._run_pagespeed_checks(
            urls=crawled_urls,
            device=device_enum,
        )

        # ── Phase 3: Persist all results ──────────────────────────────
        async with async_session_factory() as db:
            repo = LighthousePageResultRepository(db)
            for r in results:
                status_enum = (
                    PageStatus.SUCCESS
                    if r["status"] == "success"
                    else PageStatus.FAILED
                )
                await repo.insert(
                    check_id=check_id,
                    domain=domain,
                    url=r["url"],
                    device=device_enum,
                    status=status_enum,
                    reason=r.get("reason"),
                    performance_score=r.get("performance_score"),
                    seo_score=r.get("seo_score"),
                    fcp_ms=r.get("fcp_ms"),
                    lcp_ms=r.get("lcp_ms"),
                    tbt_ms=r.get("tbt_ms"),
                    cls=r.get("cls"),
                )
            await db.commit()

            logger.info(
                f"LighthouseCheckService: persisted {len(results)} results "
                f"for check_id={check_id}"
            )

        return {
            "check_id": str(check_id),
            "domain": domain,
            "device": device,
            "urls_checked": len(results),
            "results": results,
        }

    # ── Phase 1: Crawl + collect URLs ─────────────────────────────────

    async def _crawl_and_collect(self, url: str, max_pages: int) -> list[str]:
        """
        Crawl the seed URL via CrawlOrchestrator, then collect all
        successfully crawled internal HTML page URLs from the database.

        The CrawlOrchestrator:
          - Phase A: fetches robots.txt + sitemaps (SiteDiscoveryService),
            extracts all page URLs listed in sitemaps
          - Phase B: if sitemap yielded few URLs, does BFS traversal of
            internal <a> links from the seed page up to max_depth hops
          - Persists every crawled URL into the crawl_pages table

        After the crawl, CrawlPageRepository.get_by_audit_id(audit_id)
        returns all discovered+visited pages. We filter to successful
        HTML pages (is_success=True, 200 <= status_code < 400).
        """
        async with async_session_factory() as db:
            # Create a CrawlJob row — the orchestrator requires it
            crawl_job = CrawlJob(
                id=uuid4(),
                user_id=uuid4(),  # no auth context in this flow; placeholder UUID
                url=url,
                domain=get_domain(url) or "",
                status="queued",
                max_pages=max_pages,
                max_depth=3,
                crawl_config={
                    "max_pages": max_pages,
                    "max_depth": 3,
                    "concurrency": 10,
                    "request_timeout": 60,
                    "respect_robots": True,
                    "auto_analyze": False,
                },
            )
            job_repo = CrawlJobRepository(db)
            await job_repo.create(crawl_job)
            await db.commit()

            # Run the full crawl via the same orchestrator used by
            # POST /crawler/crawl
            orchestrator = CrawlOrchestrator(db, crawl_job.id)
            await orchestrator.run(
                start_url=url,
                max_pages=max_pages,
                max_depth=3,
            )

            # Collect all crawled pages for this job
            page_repo = CrawlPageRepository(db)
            pages: list[CrawlPage] = await page_repo.get_by_audit_id(crawl_job.id)

            # Filter: only successful HTML pages, dedupe, preserve order
            seen: set[str] = set()
            valid_urls: list[str] = []
            for page in pages:
                if not page.is_success:
                    continue
                if page.status_code is None or not (200 <= page.status_code < 400):
                    continue
                norm = page.normalized_url or page.url
                if norm and norm not in seen:
                    seen.add(norm)
                    valid_urls.append(norm)

            # Ensure the seed URL is always first (for consistent reporting)
            seed_norm = normalize_url(url)
            if seed_norm in valid_urls:
                valid_urls.remove(seed_norm)
                valid_urls.insert(0, seed_norm)

            return valid_urls

    # ── Phase 2: Pagespeed API checks ─────────────────────────────────

    async def _run_pagespeed_checks(
        self,
        urls: list[str],
        device: Device,
    ) -> list[dict]:
        """
        Call Google PageSpeed Insights API for each URL concurrently.

        Uses an asyncio.Semaphore to stay within rate limits.
        Failed calls are recorded with status="failed" and a reason,
        not raised as exceptions — so one failure does not abort the batch.
        """
        semaphore = asyncio.Semaphore(self.PAGESPEED_CONCURRENCY)
        strategy = device.value  # "mobile" or "desktop"

        async def _check_one(target_url: str) -> dict:
            async with semaphore:
                try:
                    raw = await self.pagespeed_client.fetch(
                        url=target_url,
                        strategy=strategy,
                    )
                    parsed = PagespeedClient.parse_result(
                        raw, target_url, strategy
                    )
                    parsed["status"] = "success"
                    logger.info(
                        f"Pagespeed check OK: {target_url} "
                        f"(perf={parsed.get('performance_score')})"
                    )
                    return parsed
                except httpx.HTTPStatusError as e:
                    logger.warning(
                        f"Pagespeed API error for {target_url}: "
                        f"status={e.response.status_code}"
                    )
                    return {
                        "url": target_url,
                        "device": strategy,
                        "status": "failed",
                        "reason": f"API error: {e.response.status_code}",
                    }
                except Exception as e:
                    logger.error(
                        f"Pagespeed check failed for {target_url}: {e}",
                        exc_info=True,
                    )
                    return {
                        "url": target_url,
                        "device": strategy,
                        "status": "failed",
                        "reason": str(e)[:255],
                    }

        tasks = [_check_one(u) for u in urls]
        results = await asyncio.gather(*tasks)
        return list(results)
