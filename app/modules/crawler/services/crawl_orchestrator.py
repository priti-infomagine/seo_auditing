"""
Crawl orchestrator - controls the entire crawl lifecycle.

Orchestrates all services to perform a complete recursive crawl:
  1. Create a CrawlJob + CrawlConfig in the database.
  2. Seed the CrawlQueueService with the start URL.
  3. BFS crawl loop with bounded concurrency (asyncio.Semaphore).
  4. For every URL: fetch -> process -> persist page -> extract links/
     assets -> store snapshot -> checksum -> enqueue new internal links.
  5. Update CrawlJob status and duration on completion.

All crawl logic lives here -- no parsing or scoring concerns.
"""
import asyncio
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.modules.crawler.extractors.asset_extractor import extract_assets
from app.modules.crawler.extractors.link_extractor import extract_links
from app.modules.crawler.extractors.redirect_extractor import (
    extract_redirect_chain,
)
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.services.asset_service import AssetService
from app.modules.crawler.services.checksum_service import ChecksumService
from app.modules.crawler.services.crawl_config_service import CrawlConfigService
from app.modules.crawler.services.crawl_error_service import CrawlErrorService
from app.modules.crawler.services.crawl_queue_service import CrawlQueueService
from app.modules.crawler.services.fetch_service import FetchResult, fetch_page
from app.modules.crawler.services.link_service import LinkService
from app.modules.crawler.services.page_service import PageService
from app.modules.crawler.services.redirect_service import RedirectService
from app.modules.crawler.services.response_service import (
    ProcessedResponse,
    process_response,
)
from app.modules.crawler.services.snapshot_service import SnapshotService
from app.modules.crawler.services.crawl_statistics_service import CrawlStatisticsService
from app.shared.utils.url_utils import get_domain, normalize_url, is_internal_link
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.models.crawl_config import CrawlConfig


class CrawlOrchestrator:
    """Orchestrates the entire crawl lifecycle."""

    def __init__(self, db, crawl_job_id: UUID):
        self.db = db
        self.crawl_job_id = crawl_job_id
        self.job_repository = CrawlJobRepository(db)
        self.config_service = CrawlConfigService(db)
        self.page_service = PageService(db, crawl_job_id)
        self.snapshot_service = SnapshotService(db)
        self.error_service = CrawlErrorService(db)
        self.checksum_service = ChecksumService(db)
        self.statistics_service = CrawlStatisticsService(db)
        self.queue_service: Optional[CrawlQueueService] = None
        self.config: Optional[CrawlConfig] = None

    # -- public API ---------------------------------------------------

    async def run(
        self,
        start_url: str,
        max_depth: int = 5,
        max_pages: int = 1000,
        concurrency: int = 10,
        timeout_seconds: int = 30,
        delay_ms: int = 0,
        follow_redirects: bool = True,
        respect_robots: bool = True,
        user_agent: Optional[str] = None,
    ) -> dict:
        """
        Run a full recursive crawl.

        Args:
            start_url: Entry-point URL.
            max_depth: Maximum crawl depth.
            max_pages: Maximum number of pages to crawl.
            concurrency: Number of concurrent requests.
            timeout_seconds: Per-request timeout.
            delay_ms: Delay between requests (ms).
            follow_redirects: Whether to follow HTTP redirects.
            respect_robots: Whether to honour robots.txt.
            user_agent: Custom User-Agent header.

        Returns:
            Summary dict from CrawlStatisticsService.
        """
        start_time = time.time()
        await self._mark_running()

        # Create / fetch crawl configuration
        self.config = await self.config_service.create_config(
            crawl_id=self.crawl_job_id,
            max_depth=max_depth,
            max_pages=max_pages,
            concurrency=concurrency,
            timeout_seconds=timeout_seconds,
            delay_ms=delay_ms,
            follow_redirects=follow_redirects,
            respect_robots=respect_robots,
            user_agent=user_agent,
        )

        # Determine the base domain for internal-link filtering
        start_domain = get_domain(start_url)

        # Initialise the BFS queue with domain filtering
        self.queue_service = CrawlQueueService(
            max_depth=self.config.max_depth,
            max_pages=self.config.max_pages,
            base_domain=start_domain,
        )
        self.queue_service.add_url(start_url, depth=0)

        # Bounded-concurrency semaphore
        semaphore = asyncio.Semaphore(self.config.concurrency)

        # Crawl loop
        tasks: list[asyncio.Task] = []
        while not self.queue_service.is_empty:
            item = self.queue_service.get_next()
            if item is None:
                break
            task = asyncio.create_task(
                self._crawl_with_semaphore(semaphore, item, start_url)
            )
            tasks.append(task)

            # Optional crawl delay
            if self.config.delay_ms:
                await asyncio.sleep(self.config.delay_ms / 1000.0)

        # Wait for all in-flight tasks
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Finalise
        duration_ms = int((time.time() - start_time) * 1000)
        await self._mark_completed(duration_ms)

        return await self.statistics_service.get_crawl_summary(self.crawl_job_id)

    async def crawl_page(
        self,
        url: str,
        depth: int = 0,
        parent_page_id: Optional[UUID] = None,
    ) -> None:
        """
        Crawl a single page and process it.

        Args:
            url: URL to crawl
            depth: Current crawl depth
            parent_page_id: Parent page ID for hierarchy
        """
        try:
            # Fetch the page
            fetch_result = await fetch_page(
                url,
                timeout=self._timeout,
                follow_redirects=self._follow_redirects,
                user_agent=self._user_agent,
            )

            if fetch_result.error:
                await self.error_service.log_error(
                    self.crawl_job_id,
                    parent_page_id,
                    "fetch_error",
                    fetch_result.error,
                )
                return

            # Process response
            processed = process_response(fetch_result)
            if not processed:
                return

            # Create or update page
            normalized_url = normalize_url(url)
            page = await self.page_service.create_or_update_page(
                url=url,
                normalized_url=normalized_url,
                metadata=processed.metadata,
                parent_page_id=parent_page_id,
                depth=depth,
            )

            # Store snapshot
            html_content = processed.content.decode("utf-8", errors="ignore")
            await self.snapshot_service.store_snapshot(page.id, html_content)

            # Generate checksum
            await self.checksum_service.generate_and_save_checksum(page.id, processed.content)

            # Process redirects
            await self._process_redirects(fetch_result, page.id)

            # Extract and save links + assets (HTML only)
            if self._is_html(processed):
                extracted_links = extract_links(html_content, url)
                await self._process_links(extracted_links, page.id, page.url, depth)

                extracted_assets = extract_assets(html_content, url)
                await self._process_assets(extracted_assets, page.id, page.url)

        except Exception as e:
            await self.error_service.log_error(
                self.crawl_job_id,
                parent_page_id,
                "crawl_error",
                str(e),
            )

    async def get_summary(self) -> Optional[dict]:
        """Get crawl summary."""
        return await self.statistics_service.get_crawl_summary(self.crawl_job_id)

    # -- private helpers ----------------------------------------------

    @property
    def _timeout(self) -> int:
        return self.config.timeout_seconds if self.config else 30

    @property
    def _follow_redirects(self) -> bool:
        return self.config.follow_redirects if self.config else True

    @property
    def _user_agent(self) -> Optional[str]:
        return self.config.user_agent if self.config else None

    @staticmethod
    def _is_html(processed: ProcessedResponse) -> bool:
        ct = processed.metadata.content_type or ""
        return "text/html" in ct

    async def _mark_running(self) -> None:
        """Mark the crawl job as 'running'."""
        await self._set_status("running")

    async def _mark_completed(self, duration_ms: int) -> None:
        """Mark the crawl job as 'completed' with duration."""
        await self._finalize_status("completed", duration_ms)

    async def _set_status(self, status: str) -> None:
        job = await self.job_repository.get_by_id(self.crawl_job_id)
        if job:
            if status == "running" and not job.started_at:
                job.started_at = datetime.now(timezone.utc)
            job.status = status
            await self.job_repository.update(job)

    async def _finalize_status(self, status: str, duration_ms: int) -> None:
        job = await self.job_repository.get_by_id(self.crawl_job_id)
        if job:
            job.status = status
            job.completed_at = datetime.now(timezone.utc)
            job.duration_ms = duration_ms
            await self.job_repository.update(job)

    async def _crawl_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        item,
        base_url: str,
    ) -> None:
        """Crawl a single queue item under the concurrency semaphore."""
        async with semaphore:
            await self.crawl_page(
                item.url, depth=item.depth, parent_page_id=item.parent_page_id
            )

    async def _process_redirects(
        self,
        fetch_result: FetchResult,
        page_id: UUID,
    ) -> None:
        """Extract redirect chain and update the page's final_url."""
        redirects = []
        if fetch_result._response is not None:
            redirects = extract_redirect_chain(fetch_result._response)
        if redirects:
            redirect_service = RedirectService(self.db, page_id)
            await redirect_service.process_and_save_redirects(redirects)

    async def _process_links(
        self,
        extracted_links,
        page_id: UUID,
        page_url: str,
        depth: int,
    ) -> None:
        """Persist extracted links and enqueue internal ones for further crawl."""
        link_service = LinkService(self.db, page_id, page_url)
        await link_service.process_and_save_links(extracted_links)

        # Enqueue new internal links within the domain
        base_domain = get_domain(page_url)
        if self.queue_service and self.config:
            next_depth = depth + 1
            for link in extracted_links:
                if next_depth > self.config.max_depth:
                    break
                # Only enqueue internal links to stay within domain
                if is_internal_link(base_domain, link.url):
                    self.queue_service.add_url(
                        link.url,
                        depth=next_depth,
                        parent_page_id=page_id,
                    )

    async def _process_assets(
        self,
        extracted_assets,
        page_id: UUID,
        page_url: str,
    ) -> None:
        """Persist extracted assets."""
        asset_service = AssetService(self.db, page_id)
        await asset_service.process_and_save_assets(extracted_assets)
