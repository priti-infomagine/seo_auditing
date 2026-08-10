"""
Crawl persistence service - persists all structured crawl facts to PostgreSQL.

This service:
1. Receives structured facts from orchestrator
2. Writes to repositories:
   - CrawlJob status updates
   - CrawlPage create/update
   - PageSEOData upsert
   - PageResource bulk create
   - PageNetworkData upsert
   - CrawlSiteData upsert
   - PageSnapshot store
   - CrawlError log
   - PageLink bulk create
3. Returns persistence results

It does NOT:
- Make HTTP requests
- Parse HTML
- Run SEO rules
"""
from typing import Optional
from uuid import UUID

from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.page_seo_data import PageSEOData
from app.modules.crawler.models.page_resources import PageResource
from app.modules.crawler.models.page_network_data import PageNetworkData
from app.modules.crawler.models.crawl_site_data import CrawlSiteData
from app.modules.crawler.models.page_snapshots import PageSnapshot
from app.modules.crawler.models.crawl_errors import CrawlError
from app.modules.crawler.models.page_links import PageLink
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.repositories.crawl_page_repository import CrawlPageRepository
from app.modules.crawler.repositories.page_seo_data_repository import PageSEODataRepository
from app.modules.crawler.repositories.page_resource_repository import PageResourceRepository
from app.modules.crawler.repositories.page_network_data_repository import PageNetworkDataRepository
from app.modules.crawler.repositories.crawl_site_data_repository import CrawlSiteDataRepository
from app.modules.crawler.repositories.page_snapshot_repository import PageSnapshotRepository
from app.modules.crawler.repositories.crawl_error_repository import CrawlErrorRepository
from app.modules.crawler.repositories.page_link_repository import PageLinkRepository


class CrawlPersistenceService:
    """Service for persisting crawl data."""

    def __init__(self, db, crawl_job_id: UUID):
        self.db = db
        self.crawl_job_id = crawl_job_id
        self.job_repo = CrawlJobRepository(db)
        self.page_repo = CrawlPageRepository(db)
        self.seo_repo = PageSEODataRepository(db)
        self.resource_repo = PageResourceRepository(db)
        self.network_repo = PageNetworkDataRepository(db)
        self.site_repo = CrawlSiteDataRepository(db)
        self.snapshot_repo = PageSnapshotRepository(db)
        self.error_repo = CrawlErrorRepository(db)
        self.link_repo = PageLinkRepository(db)

    async def update_job_status(
        self,
        status: str,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update crawl job status."""
        job = await self.job_repo.get_by_id(self.crawl_job_id)
        if job:
            job.status = status
            if duration_ms is not None:
                job.duration_ms = duration_ms
            if error is not None:
                job.error = error[:1024]
            await self.job_repo.update(job)

    async def persist_page(self, page: CrawlPage) -> CrawlPage:
        """Persist a crawl page."""
        existing = await self.page_repo.get_by_url(page.crawl_id, page.normalized_url)
        if existing:
            for key, value in page.__dict__.items():
                if key not in ("id", "crawl_id", "created_at", "updated_at", "_sa_instance_state"):
                    setattr(existing, key, value)
            return await self.page_repo.update(existing)
        return await self.page_repo.create(page)

    async def persist_seo_data(self, seo_data: PageSEOData) -> PageSEOData:
        """Persist SEO data."""
        return await self.seo_repo.upsert(seo_data)

    async def persist_resources(self, page_id: UUID, resources: list) -> list:
        """Persist page resources."""
        if not resources:
            return []
        resource_objects = [
            PageResource(page_id=page_id, **r)
            for r in resources
            if isinstance(r, dict)
        ]
        return await self.resource_repo.create_batch(resource_objects)

    async def persist_network_data(self, network_data: PageNetworkData) -> PageNetworkData:
        """Persist network data."""
        return await self.network_repo.upsert(network_data)

    async def persist_site_data(self, site_data: CrawlSiteData) -> CrawlSiteData:
        """Persist site data."""
        return await self.site_repo.upsert(site_data)

    async def persist_snapshot(self, page_id: UUID, html_content: str) -> PageSnapshot:
        """Persist HTML snapshot."""
        from app.shared.utils.html_compressor import compress_html, should_compress
        content_to_store = html_content
        compressed = False
        if should_compress(html_content):
            content_to_store = compress_html(html_content)
            compressed = True
        return await self.snapshot_repo.save_snapshot(page_id, content_to_store, compressed)

    async def persist_error(
        self,
        page_id: Optional[UUID],
        error_type: str,
        error_message: str,
    ) -> CrawlError:
        """Persist crawl error."""
        error = CrawlError(
            crawl_id=self.crawl_job_id,
            page_id=page_id,
            error_type=error_type,
            error_message=error_message,
        )
        return await self.error_repo.create(error)

    async def persist_links(self, page_id: UUID, links: list) -> list:
        """Persist page links."""
        if not links:
            return []
        link_objects = [
            PageLink(
                page_id=page_id,
                crawl_job_id=self.crawl_job_id,
                target_url=link.get("url", ""),
                normalized_target_url=link.get("url"),
                anchor_text=link.get("anchor_text"),
                rel=link.get("rel"),
                link_type=link.get("link_type", "anchor"),
                is_internal=link.get("is_internal", True),
                is_external=link.get("is_external", False),
                nofollow=link.get("nofollow", False),
                ugc=link.get("ugc", False),
                sponsored=link.get("sponsored", False),
                is_crawlable=link.get("is_internal", True),
            )
            for link in links
            if isinstance(link, dict)
        ]
        return await self.link_repo.create_batch(link_objects)
