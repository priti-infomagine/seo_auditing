"""
Crawl config service - manages crawl settings.
Business logic for crawl configuration.
"""
from typing import Optional
from uuid import UUID

from app.services.crawler_service.repositories.crawl_config_repository import CrawlConfigRepository
from app.models.crawler_models.crawl_config import CrawlConfig


class CrawlConfigService:
    """Service for crawl configuration operations."""

    def __init__(self, db):
        self.repository = CrawlConfigRepository(db)

    async def create_config(
        self,
        crawl_id: UUID,
        max_depth: int = 5,
        max_pages: int = 1000,
        concurrency: int = 10,
        timeout_seconds: int = 30,
        delay_ms: int = 0,
        follow_redirects: bool = True,
        respect_robots: bool = True,
        user_agent: Optional[str] = None,
    ) -> CrawlConfig:
        """
        Create crawl configuration.

        Args:
            crawl_id: Crawl job ID
            max_depth: Maximum crawl depth
            max_pages: Maximum pages to crawl
            concurrency: Concurrent requests
            timeout_seconds: Request timeout
            delay_ms: Delay between requests
            follow_redirects: Whether to follow redirects
            respect_robots: Whether to respect robots.txt
            user_agent: User agent string

        Returns:
            Created CrawlConfig instance
        """
        config = CrawlConfig(
            crawl_id=crawl_id,
            max_depth=max_depth,
            max_pages=max_pages,
            concurrency=concurrency,
            timeout_seconds=timeout_seconds,
            delay_ms=delay_ms,
            follow_redirects=follow_redirects,
            respect_robots=respect_robots,
            user_agent=user_agent,
        )
        return await self.repository.create(config)

    async def get_config(self, crawl_id: UUID) -> Optional[CrawlConfig]:
        """Get configuration for a crawl job."""
        return await self.repository.get_by_crawl_id(crawl_id)
