"""
CrawlScheduler - Dynamic asynchronous worker pool scheduler for recursive crawling.
Terminates ONLY when queue is empty AND active_workers == 0.
"""
import asyncio
from typing import Awaitable, Callable, Dict, List, Optional, Set
from urllib.parse import urlparse
from uuid import UUID

from app.core.logger import logger
from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.services.deduplication_service import DeduplicationService
from app.modules.crawler.types import DiscoveredURL
from app.modules.crawler.utils.url import normalize_url_canonical
from app.modules.crawler.utils.url_classifier import UrlClassification, classify_url
from app.shared.utils.url_utils import normalize_host


# Map a UrlClassification to its diagnostic counter key.  Each rejected
# URL increments exactly one counter so the breakdown is consistent.
_CLASSIFICATION_TO_DIAGNOSTIC: Dict[str, str] = {
    UrlClassification.EXTERNAL: "external_host",
    UrlClassification.RESOURCE: "resource",
    UrlClassification.API: "api",
    UrlClassification.INVALID: "invalid_url",
    UrlClassification.FRAGMENT: "invalid_url",
    UrlClassification.IGNORED: "non_html",
    UrlClassification.ROBOTS: "non_html",
    UrlClassification.SITEMAP: "non_html",
}

# Counter keys always present in diagnostics output.
_DEFAULT_DIAGNOSTIC_KEYS = (
    "external_host",
    "duplicate",
    "non_html",
    "resource",
    "api",
    "max_depth",
    "max_pages",
    "invalid_url",
    "robots_blocked",
)


class CrawlScheduler:
    """Dynamic bounded async worker scheduler."""

    def __init__(
        self,
        config: CrawlConfig,
        worker_func: Callable[[DiscoveredURL], Awaitable[None]],
        base_domain: str = "",
    ):
        self.config = config
        self.worker_func = worker_func
        self.base_domain = normalize_host(base_domain) if base_domain else ""

        self.queue: asyncio.Queue[DiscoveredURL] = asyncio.Queue()
        self.dedup = DeduplicationService()
        self.active_workers: int = 0
        self.pages_crawled_count: int = 0
        self.pages_discovered_count: int = 0
        self.pages_failed_count: int = 0
        self.cancelled: bool = False

        self._condition = asyncio.Condition()
        self._http_semaphore = asyncio.Semaphore(self.config.http_concurrency)
        self._browser_semaphore = asyncio.Semaphore(self.config.browser_concurrency)

        # -- Crawl rejection diagnostics ---------------------------------
        self._diagnostics: Dict[str, int] = {
            key: 0 for key in _DEFAULT_DIAGNOSTIC_KEYS
        }
        # Optional robots policy for robots_blocked accounting.
        self._robots_policy: Optional[object] = None
        self._robots_user_agent: str = (
            getattr(config, "user_agent", None) or "*"
        )

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------
    @property
    def http_semaphore(self) -> asyncio.Semaphore:
        return self._http_semaphore

    @property
    def browser_semaphore(self) -> asyncio.Semaphore:
        return self._browser_semaphore

    @property
    def url_diagnostics(self) -> Dict[str, int]:
        """Return a snapshot of URL rejection / acceptance diagnostics."""
        return dict(self._diagnostics)

    # ------------------------------------------------------------------
    # Base-domain management
    # ------------------------------------------------------------------
    def set_base_domain(self, host: str) -> None:
        """
        Update the crawl base host (e.g. after following the seed redirect
        chain).  The host is normalized so that apex / ``www.`` variants
        compare equally.
        """
        self.base_domain = normalize_host(host)

    def set_base_domain_from_url(self, url: str) -> None:
        """Update the crawl base host from the host of *url*."""
        parsed = urlparse(url)
        host = parsed.hostname or parsed.netloc
        self.set_base_domain(host)

    def set_robots_policy(self, policy: object) -> None:
        """
        Optionally attach a robots policy so the scheduler can record
        ``robots_blocked`` rejections.  When no policy is set no
        robots enforcement occurs (backward compatible).
        """
        self._robots_policy = policy

    # ------------------------------------------------------------------
    # Diagnostics helpers
    # ------------------------------------------------------------------
    def _record_rejection(self, key: str, url: str = "") -> None:
        """Increment a diagnostic counter and emit a concise debug log."""
        if key in self._diagnostics:
            self._diagnostics[key] += 1
        else:
            self._diagnostics["non_html"] += 1
        if url:
            logger.debug("URL rejected [%s]: %s", key, url)

    @staticmethod
    def _classification_to_diagnostic(classification: str) -> str:
        """Map a UrlClassification to its diagnostic counter key."""
        return _CLASSIFICATION_TO_DIAGNOSTIC.get(classification, "non_html")

    def _is_robots_blocked(self, canonical: str) -> bool:
        """Check robots policy (if configured)."""
        if self._robots_policy is None:
            return False
        path = urlparse(canonical).path or "/"
        try:
            return not self._robots_policy.is_allowed(path, self._robots_user_agent)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------
    def submit_seed(self, seed_url: str) -> bool:
        """Submit initial seed URL to scheduler."""
        try:
            canonical = normalize_url_canonical(seed_url)
        except Exception:
            self._record_rejection("invalid_url", seed_url)
            return False

        if self.dedup.is_url_visited(canonical):
            self._record_rejection("duplicate", seed_url)
            return False

        item = DiscoveredURL(
            url=seed_url,
            normalized_url=canonical,
            source_url=seed_url,
            source_type="seed",
            depth=0,
        )
        self.dedup.mark_url_visited(canonical)
        self.pages_discovered_count += 1
        self.queue.put_nowait(item)
        return True

    def submit_discovered_url(
        self,
        url: str,
        source_url: str,
        source_type: str,
        depth: int,
        parent_page_id: Optional[UUID] = None,
    ) -> bool:
        """Submit a newly discovered child URL while workers are executing."""
        if self.cancelled:
            return False

        # -- depth guard -------------------------------------------------
        if depth > self.config.max_depth:
            self._record_rejection("max_depth", url)
            return False

        # -- URL validation (normalization may raise InvalidURLError) -----
        try:
            canonical = normalize_url_canonical(url)
        except Exception:
            self._record_rejection("invalid_url", url)
            return False

        # -- content-type / host classification --------------------------
        classification, reason = classify_url(canonical, base_domain=self.base_domain)
        if classification != UrlClassification.HTML:
            key = self._classification_to_diagnostic(classification)
            self._record_rejection(key, canonical)
            return False

        # -- robots.txt enforcement (when a policy is configured) --------
        if self._is_robots_blocked(canonical):
            self._record_rejection("robots_blocked", canonical)
            return False

        # -- deduplication -----------------------------------------------
        if self.dedup.is_url_visited(canonical):
            self._record_rejection("duplicate", canonical)
            return False

        self.dedup.mark_url_visited(canonical)
        self.pages_discovered_count += 1

        item = DiscoveredURL(
            url=url,
            normalized_url=canonical,
            source_url=source_url,
            source_type=source_type,
            depth=depth,
            parent_page_id=parent_page_id,
        )
        self.queue.put_nowait(item)
        asyncio.create_task(self._notify_condition())
        return True

    def submit_sitemap_urls(
        self,
        urls: List[str],
        source_url: str = "",
    ) -> int:
        """
        Submit sitemap-discovered page URLs into the crawl queue.

        Every URL passes through the same safety checks as HTML-discovered
        links — host eligibility, URL normalization, deduplication, HTML
        filtering, max depth, max pages, and (optionally) robots.txt.
        Sitemap XML files are classified as SITEMAP and filtered out.

        Returns the number of URLs actually enqueued.
        """
        count = 0
        for sitemap_url in urls:
            if self.submit_discovered_url(
                url=sitemap_url,
                source_url=source_url,
                source_type="sitemap",
                depth=0,
            ):
                count += 1
        return count

    async def _notify_condition(self) -> None:
        async with self._condition:
            self._condition.notify_all()

    async def run(self) -> None:
        """Run worker loop until queue == empty AND active_workers == 0."""
        workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(self.config.http_concurrency)
        ]
        await asyncio.gather(*workers, return_exceptions=True)

    async def _worker_loop(self, worker_id: int) -> None:
        while not self.cancelled:
            async with self._condition:
                while self.queue.empty() and not self.cancelled:
                    if self.active_workers == 0:
                        # Work is completely exhausted! Notify all waiting workers to exit cleanly.
                        self._condition.notify_all()
                        return
                    await self._condition.wait()

                if self.cancelled or (self.queue.empty() and self.active_workers == 0):
                    return

                try:
                    item = self.queue.get_nowait()
                except asyncio.QueueEmpty:
                    continue

                if self.pages_crawled_count >= self.config.max_pages:
                    self.queue.task_done()
                    continue

                self.active_workers += 1

            try:
                if self.config.crawl_delay_ms > 0:
                    await asyncio.sleep(self.config.crawl_delay_ms / 1000.0)

                result = await self.worker_func(item, self._http_semaphore, self._browser_semaphore)
                if result is not False:
                    self.pages_crawled_count += 1
                else:
                    self.pages_failed_count += 1
            except Exception as e:
                self.pages_failed_count += 1
                logger.error(
                    f"Worker {worker_id}: error processing {item.normalized_url}: {e}",
                    exc_info=True,
                )
            finally:
                async with self._condition:
                    self.active_workers -= 1
                    self.queue.task_done()
                    self._condition.notify_all()

    def cancel(self) -> None:
        self.cancelled = True
