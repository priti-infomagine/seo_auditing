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
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logger import logger
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

import asyncio


class CrawlPersistenceService:
    """Service for persisting crawl data."""

    def __init__(self, db, crawl_job_id: UUID, flush_every: int = 20):
        self.db = db
        self.crawl_job_id = crawl_job_id
        self._write_lock = asyncio.Lock()
        self._flush_every = flush_every
        self._buf_network: list[PageNetworkData] = []
        self._buf_seo: list[PageSEOData] = []
        self._buf_resources: list[PageResource] = []
        self._buf_links: list[PageLink] = []
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
        try:
            job = await self.job_repo.get_by_id(self.crawl_job_id)
            if job:
                job.status = status
                if duration_ms is not None:
                    job.duration_ms = duration_ms
                if error is not None:
                    job.error = error[:1024]
                await self.job_repo.update(job)
        except Exception as exc:
            logger.error(f"CrawlPersistenceService.update_job_status: error: {exc}", exc_info=True)
            raise

    async def update_progress(
        self,
        current_page: int,
        total_pages: Optional[int] = None,
    ) -> None:
        """Update crawl job progress fields and report to subscribers."""
        try:
            job = await self.job_repo.get_by_id(self.crawl_job_id)
            if not job:
                return
            if total_pages is not None:
                job.total_pages = total_pages
            job.current_page = current_page
            if total_pages and total_pages > 0:
                job.progress_percent = min(100, int((current_page / total_pages) * 100))
            else:
                job.progress_percent = None
            await self.job_repo.update(job)
        except Exception as exc:
            logger.error(f"CrawlPersistenceService.update_progress: error: {exc}", exc_info=True)

    async def persist_page(self, page: CrawlPage) -> CrawlPage:
        """Persist a crawl page."""
        try:
            async with self._write_lock:
                existing = await self.page_repo.get_by_url(page.crawl_id, page.normalized_url)
                if existing:
                    for key, value in page.__dict__.items():
                        if key not in ("id", "crawl_id", "created_at", "updated_at", "_sa_instance_state"):
                            setattr(existing, key, value)
                    return await self.page_repo.update(existing)
                return await self.page_repo.create(page)
        except Exception as exc:
            logger.error(f"CrawlPersistenceService.persist_page: error: {exc}", exc_info=True)
            raise

    async def persist_seo_data(self, seo_data: PageSEOData) -> PageSEOData:
        """Persist SEO data."""
        try:
            async with self._write_lock:
                return await self.seo_repo.upsert(seo_data)
        except Exception as exc:
            logger.error(f"CrawlPersistenceService.persist_seo_data: error: {exc}", exc_info=True)
            raise

    def _coerce_int(self, value):
        """Return an int, or None for empty/invalid values (DB Integer columns)."""
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def persist_resources(self, page_id: UUID, resources: list, page_url: str = "") -> list:
        """Persist page resources with mixed-content detection."""
        try:
            if not resources:
                return []

            resource_objects = self._build_resource_objects(page_id, resources, page_url)
            async with self._write_lock:
                return await self.resource_repo.create_batch(resource_objects)
        except Exception as exc:
            logger.error(f"CrawlPersistenceService.persist_resources: error: {exc}", exc_info=True)
            raise

    async def persist_network_data(self, network_data: PageNetworkData) -> PageNetworkData:
        """Persist network data."""
        try:
            async with self._write_lock:
                return await self.network_repo.upsert(network_data)
        except Exception as exc:
            logger.error(f"CrawlPersistenceService.persist_network_data: error: {exc}", exc_info=True)
            raise

    async def persist_site_data(self, site_data: CrawlSiteData) -> CrawlSiteData:
        """Persist site data."""
        try:
            async with self._write_lock:
                return await self.site_repo.upsert(site_data)
        except Exception as exc:
            logger.error(f"CrawlPersistenceService.persist_site_data: error: {exc}", exc_info=True)
            raise

    async def persist_snapshot(
        self,
        page_id: UUID,
        html_content: str,
        parsed_data: Optional[dict] = None,
    ) -> PageSnapshot:
        """Persist HTML snapshot."""
        try:
            from app.shared.utils.html_compressor import compress_html, should_compress
            content_to_store = html_content
            compressed = False
            if should_compress(html_content):
                content_to_store = compress_html(html_content)
                compressed = True
            async with self._write_lock:
                return await self.snapshot_repo.save_snapshot(
                    page_id, content_to_store, compressed, parsed_data=parsed_data
                )
        except Exception as exc:
            logger.error(f"CrawlPersistenceService.persist_snapshot: error: {exc}", exc_info=True)
            raise

    async def persist_error(
        self,
        page_id: Optional[UUID],
        error_type: str,
        error_message: str,
    ) -> CrawlError:
        """Persist crawl error."""
        try:
            async with self._write_lock:
                error = CrawlError(
                    crawl_id=self.crawl_job_id,
                    page_id=page_id,
                    error_type=error_type,
                    error_message=error_message,
                )
                return await self.error_repo.create(error)
        except Exception as exc:
            logger.error(f"CrawlPersistenceService.persist_error: error: {exc}", exc_info=True)
            raise

    async def persist_links(self, page_id: UUID, links: list) -> list:
        """Persist page links."""
        try:
            if not links:
                return []
            link_objects = self._build_link_objects(page_id, links)
            async with self._write_lock:
                return await self.link_repo.create_batch(link_objects)
        except Exception as exc:
            logger.error(f"CrawlPersistenceService.persist_links: error: {exc}", exc_info=True)
            raise

    # -- Buffer management -------------------------------------------------

    def set_flush_every(self, flush_every: int) -> None:
        """Update the threshold at which buffers auto-flush."""
        self._flush_every = flush_every

    def _build_resource_objects(
        self, page_id: UUID, resources: list, page_url: str = ""
    ) -> list[PageResource]:
        """Construct PageResource ORM objects (extracted from persist_resources)."""
        page_scheme = urlparse(page_url).scheme if page_url else "https"
        resource_objects = []
        for r in resources:
            if not isinstance(r, dict):
                continue
            resource = PageResource(
                page_id=page_id,
                resource_type=r.get("type", ""),
                url=r.get("url", ""),
                normalized_url=r.get("url"),
                alt=r.get("alt"),
                width=self._coerce_int(r.get("width")),
                height=self._coerce_int(r.get("height")),
                status_code=self._coerce_int(r.get("status_code")),
                size_bytes=self._coerce_int(r.get("size_bytes")),
                loading=r.get("loading"),
                srcset=r.get("srcset"),
                sizes=r.get("sizes"),
                is_lazy=r.get("is_lazy"),
                mime_type=r.get("mime_type"),
                is_mixed_content=(
                    urlparse(r.get("url", "")).scheme == "http"
                    and page_scheme == "https"
                ),
            )
            resource_objects.append(resource)
        return resource_objects

    def _build_link_objects(self, page_id: UUID, links: list) -> list[PageLink]:
        """Construct PageLink ORM objects (extracted from persist_links)."""
        return [
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

    async def buffer_network(self, network_data: PageNetworkData) -> None:
        """Buffer network data; auto-flush when threshold is reached."""
        async with self._write_lock:
            self._buf_network.append(network_data)
            if len(self._buf_network) >= self._flush_every:
                await self._flush_network_locked()

    async def buffer_seo(self, seo_data: PageSEOData) -> None:
        """Buffer SEO data; auto-flush when threshold is reached."""
        async with self._write_lock:
            self._buf_seo.append(seo_data)
            if len(self._buf_seo) >= self._flush_every:
                await self._flush_seo_locked()

    async def buffer_resources(self, page_id: UUID, resources: list, page_url: str = "") -> None:
        """Buffer page resources; auto-flush when threshold is reached."""
        async with self._write_lock:
            objs = self._build_resource_objects(page_id, resources, page_url)
            self._buf_resources.extend(objs)
            if len(self._buf_resources) >= self._flush_every:
                await self._flush_resources_locked()

    async def buffer_links(self, page_id: UUID, links: list) -> None:
        """Buffer page links; auto-flush when threshold is reached."""
        async with self._write_lock:
            objs = self._build_link_objects(page_id, links)
            self._buf_links.extend(objs)
            if len(self._buf_links) >= self._flush_every:
                await self._flush_links_locked()

    # -- Flush methods (private, called under lock) ------------------------

    async def _flush_network_locked(self) -> None:
        if not self._buf_network:
            return
        BATCH_SIZE = 500
        for start in range(0, len(self._buf_network), BATCH_SIZE):
            batch = self._buf_network[start : start + BATCH_SIZE]
            rows = [
                {
                    "page_id": r.page_id,
                    "status_code": r.status_code,
                    "content_type": r.content_type,
                    "content_length": r.content_length,
                    "response_time_ms": r.response_time_ms,
                    "headers": r.headers,
                    "redirects": r.redirects,
                    "security": r.security,
                    "performance": r.performance,
                }
                for r in batch
            ]
            stmt = pg_insert(PageNetworkData).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["page_id"],
                set_={
                    "status_code": stmt.excluded.status_code,
                    "content_type": stmt.excluded.content_type,
                    "content_length": stmt.excluded.content_length,
                    "response_time_ms": stmt.excluded.response_time_ms,
                    "headers": stmt.excluded.headers,
                    "redirects": stmt.excluded.redirects,
                    "security": stmt.excluded.security,
                    "performance": stmt.excluded.performance,
                },
            )
            await self.db.execute(stmt)
        await self.db.flush()
        self._buf_network.clear()

    async def _flush_seo_locked(self) -> None:
        if not self._buf_seo:
            return
        BATCH_SIZE = 500
        for start in range(0, len(self._buf_seo), BATCH_SIZE):
            batch = self._buf_seo[start : start + BATCH_SIZE]
            rows = [
                {
                    "page_id": r.page_id,
                    "title": r.title,
                    "title_length": r.title_length,
                    "meta_description": r.meta_description,
                    "meta_description_length": r.meta_description_length,
                    "canonical": r.canonical,
                    "robots_meta": r.robots_meta,
                    "language": r.language,
                    "charset": r.charset,
                    "viewport": r.viewport,
                    "favicon": r.favicon,
                    "word_count": r.word_count,
                    "content_hash": r.content_hash,
                    "page_metadata": r.page_metadata,
                    "headings": r.headings,
                    "content": r.content,
                    "structured_data": r.structured_data,
                    "social": r.social,
                    "indexability": r.indexability,
                    "accessibility": r.accessibility,
                }
                for r in batch
            ]
            stmt = pg_insert(PageSEOData).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["page_id"],
                set_={
                    "title": stmt.excluded.title,
                    "title_length": stmt.excluded.title_length,
                    "meta_description": stmt.excluded.meta_description,
                    "meta_description_length": stmt.excluded.meta_description_length,
                    "canonical": stmt.excluded.canonical,
                    "robots_meta": stmt.excluded.robots_meta,
                    "language": stmt.excluded.language,
                    "charset": stmt.excluded.charset,
                    "viewport": stmt.excluded.viewport,
                    "favicon": stmt.excluded.favicon,
                    "word_count": stmt.excluded.word_count,
                    "content_hash": stmt.excluded.content_hash,
                    "page_metadata": stmt.excluded.page_metadata,
                    "headings": stmt.excluded.headings,
                    "content": stmt.excluded.content,
                    "structured_data": stmt.excluded.structured_data,
                    "social": stmt.excluded.social,
                    "indexability": stmt.excluded.indexability,
                    "accessibility": stmt.excluded.accessibility,
                },
            )
            await self.db.execute(stmt)
        await self.db.flush()
        self._buf_seo.clear()

    async def _flush_resources_locked(self) -> None:
        if not self._buf_resources:
            return
        BATCH_SIZE = 500
        for start in range(0, len(self._buf_resources), BATCH_SIZE):
            batch = self._buf_resources[start : start + BATCH_SIZE]
            self.db.add_all(batch)
            await self.db.flush()
        self._buf_resources.clear()

    async def _flush_links_locked(self) -> None:
        if not self._buf_links:
            return
        BATCH_SIZE = 500
        for start in range(0, len(self._buf_links), BATCH_SIZE):
            batch = self._buf_links[start : start + BATCH_SIZE]
            self.db.add_all(batch)
            await self.db.flush()
        self._buf_links.clear()

    # -- Public flush-all --------------------------------------------------

    async def flush_all(self) -> None:
        """Flush all non-empty buffers; fault-tolerant per buffer."""
        async with self._write_lock:
            for flush_fn in (
                self._flush_network_locked,
                self._flush_seo_locked,
                self._flush_resources_locked,
                self._flush_links_locked,
            ):
                try:
                    await flush_fn()
                except Exception as exc:
                    logger.error(
                        f"CrawlPersistenceService.flush_all: {flush_fn.__name__} failed: {exc}",
                        exc_info=True,
                    )
