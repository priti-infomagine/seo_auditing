"""
Crawl statistics service - provides crawl summary.
Business logic for statistics aggregation.
"""
from typing import Optional
from uuid import UUID

from app.modules.crawler.repositories.crawl_statistics_repository import CrawlStatisticsRepository


class CrawlStatisticsService:
    """Service for crawl statistics operations."""

    def __init__(self, db):
        self.repository = CrawlStatisticsRepository(db)

    async def get_crawl_summary(self, crawl_id: UUID) -> Optional[dict]:
        """
        Get summary statistics for a crawl.

        Args:
            crawl_id: Crawl job ID

        Returns:
            Dictionary with crawl statistics
        """
        return await self.repository.get_crawl_stats(crawl_id)
