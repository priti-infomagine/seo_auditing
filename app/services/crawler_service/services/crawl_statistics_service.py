"""
Crawl statistics service - provides crawl summary.
Business logic for statistics aggregation.
"""
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

from crawler_service.repositories.crawl_statistics_repository import CrawlStatisticsRepository


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
        stats = await self.repository.get_crawl_stats(crawl_id)
        return stats