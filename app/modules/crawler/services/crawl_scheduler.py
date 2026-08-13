"""
CrawlScheduler - Dynamic asynchronous worker pool scheduler for recursive crawling.
Terminates ONLY when queue is empty AND active_workers == 0.
"""
import asyncio
from typing import Awaitable, Callable, Optional, Set
from uuid import UUID

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.services.deduplication_service import DeduplicationService
from app.modules.crawler.types import DiscoveredURL
from app.modules.crawler.utils.url import normalize_url_canonical
from app.modules.crawler.utils.url_classifier import UrlClassification, classify_url


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
        self.base_domain = base_domain.lower()

        self.queue: asyncio.Queue[DiscoveredURL] = asyncio.Queue()
        self.dedup = DeduplicationService()
        self.active_workers: int = 0
        self.pages_crawled_count: int = 0
        self.pages_discovered_count: int = 0
        self.cancelled: bool = False

        self._condition = asyncio.Condition()
        self._http_semaphore = asyncio.Semaphore(self.config.http_concurrency)
        self._browser_semaphore = asyncio.Semaphore(self.config.browser_concurrency)

    @property
    def http_semaphore(self) -> asyncio.Semaphore:
        return self._http_semaphore

    @property
    def browser_semaphore(self) -> asyncio.Semaphore:
        return self._browser_semaphore

    def submit_seed(self, seed_url: str) -> bool:
        """Submit initial seed URL to scheduler."""
        try:
            canonical = normalize_url_canonical(seed_url)
        except Exception:
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
        if depth > self.config.max_depth:
            return False
        if self.pages_discovered_count >= self.config.max_pages:
            return False

        try:
            canonical = normalize_url_canonical(url)
        except Exception:
            return False

        # Classification check
        classification, _ = classify_url(canonical, base_domain=self.base_domain)
        if classification != UrlClassification.HTML:
            return False

        if self.dedup.is_url_visited(canonical):
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

                await self.worker_func(item)
                self.pages_crawled_count += 1
            except Exception:
                pass
            finally:
                async with self._condition:
                    self.active_workers -= 1
                    self.queue.task_done()
                    self._condition.notify_all()

    def cancel(self) -> None:
        self.cancelled = True
