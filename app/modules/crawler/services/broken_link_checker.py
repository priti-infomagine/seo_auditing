"""
Broken link checker - validates HTTP status of links discovered during crawl.

Runs AFTER the crawl completes and CrawlPage/PageLink records are persisted.
Populates ``target_status_code`` on PageLink records so that:

- ``AuditResponseBuilder._build_links`` can report real broken counts
- ``RuleEvaluatorService`` can pass ``broken_internal`` / ``broken_external``
  to the ``BrokenLinksRule`` (links_003)

Internal links are resolved against already-crawled CrawlPage rows (no extra
HTTP requests needed).  External links are checked via concurrent HTTP HEAD
requests with a short timeout.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List
from urllib.parse import urlparse
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.#loggger import #loggger
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.page_links import PageLink
from app.modules.crawler.repositories.crawl_page_repository import CrawlPageRepository
from app.modules.crawler.repositories.page_link_repository import PageLinkRepository
from app.shared.utils.url_utils import normalize_url


@dataclass
class BrokenLinkStats:
    """Aggregate broken-link statistics for a single crawl job."""

    broken_internal: int = 0
    broken_external: int = 0
    total_checked: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "broken_internal": self.broken_internal,
            "broken_external": self.broken_external,
            "total_checked": self.total_checked,
            "errors": self.errors,
        }


class BrokenLinkChecker:
    """Check HTTP status of links discovered during a crawl."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.crawl_page_repo = CrawlPageRepository(db)
        self.page_link_repo = PageLinkRepository(db)

    async def check_links(self, audit_id: UUID) -> BrokenLinkStats:
        """Populate ``target_status_code`` on all PageLink rows for *audit_id*.

        1. Internal links — resolved against ``CrawlPage`` records (zero HTTP).
        2. External links — HTTP HEAD requests (concurrency-limited, short
           timeout).  Skipped entirely when ``LINK_CHECK_EXTERNAL_ENABLED``
           is ``False``.
        """
        #loggger.info(
            "BrokenLinkChecker.check_links: starting audit_id=%s", audit_id
        )

        # --- 1. Build normalized-URL → status-code map from crawled pages ---
        crawl_pages: List[CrawlPage] = await self.crawl_page_repo.get_by_audit_id(
            audit_id
        )
        page_status: Dict[str, int] = {}
        for cp in crawl_pages:
            if cp.normalized_url:
                try:
                    norm = normalize_url(cp.normalized_url)
                except Exception:
                    continue
                if cp.status_code:
                    page_status[norm] = cp.status_code

        # --- 2. Load all links for this crawl job ---
        links: List[PageLink] = await self.page_link_repo.get_by_crawl_job_id(
            audit_id
        )

        stats = BrokenLinkStats(total_checked=len(links))

        # --- 3. Resolve internal links from the crawl-page status map ---
        for link in links:
            if not link.is_internal:
                continue
            if not link.target_url:
                continue
            try:
                norm_target = normalize_url(link.target_url)
            except Exception:
                continue

            status = page_status.get(norm_target)
            if status is not None:
                link.target_status_code = status
                if status >= 400:
                    link.target_error = f"HTTP {status}"
                    stats.broken_internal += 1

        # --- 4. Check external links via HTTP HEAD ---
        if settings.LINK_CHECK_EXTERNAL_ENABLED:
            unique_externals = {
                link.target_url
                for link in links
                if link.is_external and link.target_url
            }
            if unique_externals:
                status_map = await self._check_external_urls(unique_externals)
                for link in links:
                    if not link.is_external or not link.target_url:
                        continue
                    status = status_map.get(link.target_url)
                    if status is not None:
                        link.target_status_code = status
                        if status >= 400:
                            link.target_error = f"HTTP {status}"
                            stats.broken_external += 1

        await self.db.flush()
        #loggger.info(
            "BrokenLinkChecker.check_links: done audit_id=%s stats=%s",
            audit_id,
            stats.to_dict(),
        )
        return stats

    async def _check_external_urls(
        self, urls: set
    ) -> Dict[str, int]:
        """HEAD-check a set of external URLs concurrently.

        Returns ``{url: status_code}``.  ``status_code`` is ``0`` when the
        request fails (timeout, DNS error, connection refused, etc.).
        """
        results: Dict[str, int] = {}
        semaphore = asyncio.Semaphore(settings.LINK_CHECK_MAX_CONCURRENCY)

        async def _check(url: str) -> None:
            async with semaphore:
                try:
                    async with httpx.AsyncClient(
                        timeout=settings.LINK_CHECK_TIMEOUT,
                        follow_redirects=False,
                        headers={"User-Agent": "SEOAudit-Bot/1.0"},
                    ) as client:
                        resp = await client.head(url)
                        results[url] = resp.status_code
                except httpx.TimeoutException:
                    results[url] = 0
                except Exception:
                    results[url] = 0

        await asyncio.gather(*[_check(u) for u in urls])
        return results
