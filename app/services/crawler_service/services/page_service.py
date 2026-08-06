"""
Page service - creates/updates CrawlPage records.
Business logic + validation + persistence coordination.
"""
from typing import Optional
from uuid import UUID

from app.services.crawler_service.extractors.metadata_extractor import ExtractedMetadata
from app.services.crawler_service.repositories.crawl_page_repository import CrawlPageRepository
from app.models.crawler_models.crawl_pages import CrawlPage


class PageService:
    """Service for page operations."""

    def __init__(self, db, crawl_id: UUID):
        self.repository = CrawlPageRepository(db)
        self.crawl_id = crawl_id

    async def create_or_update_page(
        self,
        url: str,
        normalized_url: str,
        metadata: ExtractedMetadata,
        parent_page_id: Optional[UUID] = None,
        depth: int = 0,
    ) -> CrawlPage:
        """
        Create or update a crawl page.

        Args:
            url: Original URL
            normalized_url: Normalized URL
            metadata: Extracted metadata
            parent_page_id: Parent page ID for hierarchy
            depth: Crawl depth

        Returns:
            CrawlPage instance
        """
        # Check if page already exists
        existing = await self.repository.get_by_url(self.crawl_id, normalized_url)

        if existing:
            # Update existing page
            existing.status_code = metadata.status_code
            existing.content_type = metadata.content_type
            existing.content_size = metadata.content_size
            existing.response_time_ms = metadata.response_time_ms
            existing.final_url = metadata.final_url
            return await self.repository.update(existing)

        # Create new page
        page = CrawlPage(
            crawl_id=self.crawl_id,
            url=url,
            normalized_url=normalized_url,
            depth=depth,
            status_code=metadata.status_code,
            final_url=metadata.final_url,
            content_type=metadata.content_type,
            content_size=metadata.content_size,
            response_time_ms=metadata.response_time_ms,
            parent_page_id=parent_page_id,
        )
        return await self.repository.create(page)

    async def get_page(self, page_id: UUID) -> Optional[CrawlPage]:
        """Get page by ID."""
        return await self.repository.get_by_id(page_id)
