"""
CrawlError repository - database operations for CrawlError model.
"""
import sys
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.crawler_models.crawl_errors import CrawlError


class CrawlErrorRepository:
    """Repository for CrawlError database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create(self, crawl_error: CrawlError) -> CrawlError:
        """Create a new crawl error."""
        self.db.add(crawl_error)
        await self.db.flush()
        await self.db.refresh(crawl_error)
        return crawl_error
    
    async def create_batch(self, crawl_errors: List[CrawlError]) -> List[CrawlError]:
        """Create multiple crawl errors."""
        self.db.add_all(crawl_errors)
        await self.db.flush()
        return crawl_errors
    
    async def get_by_crawl_id(self, crawl_id: UUID) -> List[CrawlError]:
        """Get all errors for a crawl job."""
        result = await self.db.execute(
            select(CrawlError).where(CrawlError.crawl_id == crawl_id)
        )
        return list(result.scalars().all())
    
    async def get_by_page_id(self, page_id: UUID) -> List[CrawlError]:
        """Get all errors for a page."""
        result = await self.db.execute(
            select(CrawlError).where(CrawlError.page_id == page_id)
        )
        return list(result.scalars().all())