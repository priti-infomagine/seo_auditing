"""
Crawl orchestrator - controls the entire crawl lifecycle using CrawlScheduler.

Orchestrates all services to perform a complete recursive crawl:
   1. Initialize CrawlJob
   2. Seed CrawlScheduler with start URL
   3. Dynamic worker pool with dual semaphores (http_concurrency / browser_concurrency)
   4. For every URL: page_crawl_service -> page_extraction_service -> persist
   5. Discovered links are submitted back to the scheduler during worker execution
   6. Update CrawlJob status on completion
"""
import asyncio
import hashlib
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.crawl_site_data import CrawlSiteData
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.services.crawl_scheduler import CrawlScheduler
from app.modules.crawler.services.crawl_persistence_service import CrawlPersistenceService
from app.modules.crawler.services.crawl_pipeline_events import CrawlPipelineBus, CrawlPipelineEvent
from app.modules.crawler.services.link_analysis_service import LinkAnalysisService, LinkAnalysisResult
from app.modules.crawler.services.page_crawl_service import PageCrawlService, PageCrawlResult
from app.modules.crawler.services.page_extraction_service import PageExtractionService, PageFacts
from app.modules.crawler.services.redirect_service import RedirectService
from app.modules.crawler.services.site_discovery_service import SiteDiscoveryService
from app.modules.crawler.services.technical_analysis_service import TechnicalAnalysisService
from app.modules.crawler.types import DiscoveredURL
from app.shared.utils.url_utils import get_domain, normalize_url
from app.modules.crawler.utils.url_classifier import strip_tracking_params


class CrawlOrchestrator:
    """Orchestrates the entire crawl lifecycle using CrawlScheduler."""

    def __init__(self, db, crawl_job_id: UUID):
        self.db = db
        self.crawl_job_id = crawl_job_id
        self.job_repository = CrawlJobRepository(db)
        self.persistence = CrawlPersistenceService(db, crawl_job_id)
        self.page_crawl_service = PageCrawlService()
        self.page_extraction_service = PageExtractionService()
        self.link_analysis_service = LinkAnalysisService
        self.technical_analysis_service = TechnicalAnalysisService()
        self.redirect_service_factory = lambda page_id: RedirectService(db, page_id)
        self.config: Optional[CrawlConfig] = None
        self.event_bus = CrawlPipelineBus()
        self._scheduler: Optional[CrawlScheduler] = None

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
        Run a full recursive crawl using CrawlScheduler dynamic worker pool.

        Terminates when queue is empty AND active_workers == 0,
        ensuring all dynamically discovered URLs are crawled.
        """
        start_time = time.time()
        await self._mark_running()

        job = await self.job_repository.get_by_id(self.crawl_job_id)
        if not job:
            raise ValueError(f"CrawlJob {self.crawl_job_id} not found")

        raw_config = job.crawl_config or {}
        self.config = CrawlConfig.from_dict(raw_config)

        start_domain = get_domain(start_url)

        await self.event_bus.emit(
            CrawlPipelineEvent.SCHEDULER_START,
            crawl_id=str(self.crawl_job_id),
            start_url=start_url,
            max_depth=self.config.max_depth,
            max_pages=self.config.max_pages,
        )

        if respect_robots:
            discovery = SiteDiscoveryService(start_url, timeout=timeout_seconds)
            site_result = await discovery.discover()
            await self.persistence.persist_site_data(
                CrawlSiteData(
                    crawl_job_id=self.crawl_job_id,
                    robots={
                        "exists": site_result.robots.exists,
                        "status_code": site_result.robots.status_code,
                        "user_agents": {"*": {"allow": [], "disallow": []}},
                        "sitemaps": site_result.robots.sitemap_references,
                    },
                    sitemaps={
                        "exists": len(site_result.sitemaps) > 0,
                        "files": [
                            {
                                "url": s.url,
                                "status_code": s.status_code,
                                "type": "sitemap",
                                "url_count": len(s.urls),
                            }
                            for s in site_result.sitemaps
                        ],
                    },
                )
            )

        scheduler = CrawlScheduler(
            config=self.config,
            worker_func=self._crawl_page,
            base_domain=start_domain,
        )
        self._scheduler = scheduler
        scheduler.submit_seed(start_url)

        try:
            await scheduler.run()
        except Exception as exc:
            await self._mark_failed(str(exc))
            return {"status": "failed", "crawl_id": str(self.crawl_job_id)}
        finally:
            self._scheduler = None

        duration_ms = int((time.time() - start_time) * 1000)
        await self._mark_completed(duration_ms)

        await self.event_bus.emit(
            CrawlPipelineEvent.SCHEDULER_COMPLETE,
            crawl_id=str(self.crawl_job_id),
            pages_crawled=scheduler.pages_crawled_count,
            pages_discovered=scheduler.pages_discovered_count,
            duration_ms=duration_ms,
        )

        return {
            "status": "completed",
            "crawl_id": str(self.crawl_job_id),
            "pages_crawled": scheduler.pages_crawled_count,
            "pages_discovered": scheduler.pages_discovered_count,
        }

    async def crawl_page(
        self,
        url: str,
        depth: int = 0,
        parent_page_id: Optional[UUID] = None,
    ) -> None:
        """
        Crawl a single page and process it.

        Kept for backward compatibility with test-crawler endpoint.
        """
        await self._crawl_page(
            DiscoveredURL(
                url=url,
                normalized_url=normalize_url(url),
                source_url=url,
                source_type="seed",
                depth=depth,
                parent_page_id=parent_page_id,
            ),
            http_sem=asyncio.Semaphore(self.config.http_concurrency if self.config else 10),
            browser_sem=asyncio.Semaphore(self.config.browser_concurrency if self.config else 3),
        )

    async def _crawl_page(self, item: DiscoveredURL, http_sem: asyncio.Semaphore, browser_sem: asyncio.Semaphore) -> None:
        await self.event_bus.emit(
            CrawlPipelineEvent.PAGE_START,
            url=item.normalized_url,
            depth=item.depth,
            parent_page_id=str(item.parent_page_id) if item.parent_page_id else None,
        )

        async with http_sem:
            crawl_result = await self.page_crawl_service.crawl_page(
                item.normalized_url,
                timeout=self.config.request_timeout if self.config else 30,
                follow_redirects=True,
                user_agent=self.config.user_agent if self.config else None,
            )

        await self.event_bus.emit(
            CrawlPipelineEvent.PAGE_FETCHED,
            url=item.normalized_url,
            success=crawl_result.success,
            error=crawl_result.error,
        )

        if crawl_result.error:
            await self.persistence.persist_error(
                page_id=item.parent_page_id,
                error_type=crawl_result.error_type or "crawl_error",
                error_message=crawl_result.error,
            )
            await self.event_bus.emit(
                CrawlPipelineEvent.PAGE_ERROR,
                url=item.normalized_url,
                error=crawl_result.error,
            )
            return

        document = crawl_result.document
        fetch_result = crawl_result.fetch_result
        normalized_url = crawl_result.normalized_url

        from app.modules.parser.services.parser_orchestrator import ParserOrchestrator

        parser = ParserOrchestrator()
        parsed = parser.parse(
            html=document.raw_html,
            url=normalized_url,
        )

        page_facts = self.page_extraction_service.extract_from_parsed(
            parsed_document=parsed,
            status_code=fetch_result.status_code,
            headers=fetch_result.headers,
            content_length=len(document.raw_html),
            response_time_ms=fetch_result.response_time_ms,
            redirects=[
                {"url": r.url, "status_code": r.status_code}
                for r in fetch_result.redirect_chain
            ],
        )

        if parsed.content and parsed.content.text:
            page_facts.content.content_hash = hashlib.md5(parsed.content.text.encode()).hexdigest()
            page_facts.content.sentence_count = max(
                page_facts.content.sentence_count,
                len([s for s in parsed.content.text.replace("!", ".").replace("?", ".").split(".") if s.strip()])
            )

        link_analysis = self.link_analysis_service(item.normalized_url)
        link_result = await link_analysis.analyze(page_facts.links)

        redirect_chain = fetch_result.redirect_chain

        technical_analysis = self.technical_analysis_service()
        technical_result = await technical_analysis.analyze(
            page_facts.technical,
            content_bytes=fetch_result.content,
            url=normalized_url,
        )

        parsed_url = urlparse(normalized_url)
        url_hash = hashlib.md5(normalized_url.encode()).hexdigest()

        page = CrawlPage(
            crawl_id=self.crawl_job_id,
            url=item.url,
            normalized_url=normalized_url,
            url_hash=url_hash,
            scheme=parsed_url.scheme,
            host=parsed_url.netloc,
            path=parsed_url.path,
            query=parsed_url.query,
            final_url=fetch_result.final_url,
            depth=item.depth,
            status_code=technical_result.status_code,
            content_type=technical_result.content_type,
            content_length=technical_result.content_length,
            response_time_ms=technical_result.response_time_ms,
            parent_page_id=item.parent_page_id,
            is_crawled=True,
            is_success=200 <= technical_result.status_code < 400,
            is_redirect=len(redirect_chain) > 0,
            is_error=technical_result.status_code >= 400,
        )
        page = await self.persistence.persist_page(page)

        await self.persistence.persist_snapshot(page.id, document.raw_html)

        await self.persistence.persist_network_data(
            page_network_data=PageNetworkData(
                page_id=page.id,
                status_code=technical_result.status_code,
                content_type=technical_result.content_type,
                content_length=technical_result.content_length,
                response_time_ms=technical_result.response_time_ms,
                headers=technical_result.headers,
                redirects=technical_result.redirects,
                security=technical_result.security,
                performance=technical_result.performance,
            )
        )

        page_metadata = {
            "meta_tags": [
                {"name": t.name, "content": t.content}
                for t in (page_facts.metadata.meta_tags or [])
            ],
            "open_graph": page_facts.metadata.open_graph or {},
            "twitter": page_facts.metadata.twitter or {},
            "hreflang": [
                {"url": h.get("url", ""), "hreflang": h.get("hreflang", "")}
                for h in (page_facts.metadata.hreflang or [])
            ],
        }
        googlebot_content = ""
        for t in (page_facts.metadata.robots or []):
            if t.name == "googlebot":
                googlebot_content = t.content
                break
        if googlebot_content:
            page_metadata["googlebot"] = googlebot_content

        await self.persistence.persist_seo_data(
            page_seo_data=PageSEOData(
                page_id=page.id,
                title=page_facts.metadata.title,
                title_length=page_facts.metadata.title_length,
                meta_description=page_facts.metadata.meta_description,
                meta_description_length=page_facts.metadata.meta_description_length,
                canonical=page_facts.metadata.canonical,
                robots_meta=page_facts.metadata.robots_meta,
                language=page_facts.metadata.language or document.language,
                charset=page_facts.metadata.charset or document.charset,
                viewport=page_facts.metadata.viewport,
                favicon=page_facts.metadata.favicon,
                word_count=page_facts.content.word_count,
                content_hash=page_facts.content.content_hash,
                headings=page_facts.content.headings,
                content={
                    "text": page_facts.content.text,
                    "word_count": page_facts.content.word_count,
                    "character_count": len(page_facts.content.text),
                    "paragraph_count": page_facts.content.paragraph_count,
                    "sentence_count": page_facts.content.sentence_count,
                    "language": document.language,
                    "content_hash": page_facts.content.content_hash,
                },
                structured_data={
                    "exists": len(technical_result.json_ld) > 0,
                    "items": technical_result.json_ld,
                    "types": [item.get("type") for item in technical_result.json_ld],
                },
                social={
                    "open_graph": page_facts.metadata.open_graph,
                    "twitter": page_facts.metadata.twitter,
                },
                indexability={
                    "robots_meta": page_facts.metadata.robots_meta,
                    "canonical": page_facts.metadata.canonical,
                },
                accessibility=technical_result.accessibility,
                page_metadata=page_metadata,
            )
        )

        await self.persistence.persist_resources(page.id, page_facts.resources.resources, page_url=normalized_url)
        await self.persistence.persist_links(page.id, link_result.links)

        redirect_links = link_result.redirect_links
        if redirect_links:
            redirect_service = self.redirect_service_factory(page.id)
            await redirect_service.process_and_save_redirects(redirect_links)

        if document.is_html:
            self._enqueue_links(link_result.links, page.id, item.normalized_url, item.depth)

        await self.event_bus.emit(
            CrawlPipelineEvent.PAGE_PERSISTED,
            url=item.normalized_url,
            page_id=str(page.id),
        )

    async def get_summary(self) -> Optional[dict]:
        """Get crawl summary."""
        return {"status": "completed", "crawl_id": str(self.crawl_job_id)}

    # -- private helpers ----------------------------------------------

    async def _mark_running(self) -> None:
        await self._set_status("crawling")

    async def _mark_completed(self, duration_ms: int) -> None:
        await self._finalize_status("completed", duration_ms)

    async def _mark_failed(self, error_message: str) -> None:
        job = await self.job_repository.get_by_id(self.crawl_job_id)
        if job and job.status not in ("completed", "failed", "cancelled"):
            job.status = "failed"
            job.error = error_message[:1024]
            job.completed_at = datetime.now(timezone.utc)
            await self.job_repository.update(job)

    async def _set_status(self, status: str) -> None:
        job = await self.job_repository.get_by_id(self.crawl_job_id)
        if job:
            if status == "crawling" and not job.started_at:
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

    def _enqueue_links(
        self,
        links: list,
        page_id: UUID,
        page_url: str,
        depth: int,
    ) -> None:
        if not self._scheduler or not self.config:
            return

        next_depth = depth + 1
        max_depth = self.config.max_depth

        for link in links:
            if next_depth > max_depth:
                break
            if link.get("is_internal"):
                raw_url = link["url"]
                clean_url = strip_tracking_params(raw_url)
                self._scheduler.submit_discovered_url(
                    url=clean_url,
                    source_url=page_url,
                    source_type="html_link",
                    depth=next_depth,
                    parent_page_id=page_id,
                )
