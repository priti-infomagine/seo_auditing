"""
CrawlStatistics repository - database operations for crawl statistics.
"""
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.crawler_models.crawl_jobs import CrawlJob


class CrawlStatisticsRepository:
    """Repository for crawl statistics operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_crawl_stats(self, crawl_id: UUID) -> Optional[dict]:
        """Get statistics for a crawl job."""
        # This would typically aggregate data from multiple tables
        # For now, return basic job info
        result = await self.db.execute(
            select(CrawlJob).where(CrawlJob.id == crawl_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            return None
        
        return {
            "crawl_id": crawl_id,
            "domain": job.domain,
            "status": job.status,
            "duration_ms": job.duration_ms,
        }