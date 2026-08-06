"""
CrawlPage repository - database operations for CrawlPage model.
"""
import sys
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.modules.crawler.models.crawl_pages import CrawlPage


class CrawlPageRepository:
    """Repository for CrawlPage database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create(self, crawl_page: CrawlPage) -> CrawlPage:
        """Create a new crawl page."""
        self.db.add(crawl_page)
        await self.db.flush()
        await self.db.refresh(crawl_page)
        return crawl_page
    
    async def get_by_id(self, page_id: UUID) -> Optional[CrawlPage]:
        """Get crawl page by ID."""
        result = await self.db.execute(
            select(CrawlPage).where(CrawlPage.id == page_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_crawl_id(self, crawl_id: UUID) -> List[CrawlPage]:
        """Get all pages for a crawl job."""
        result = await self.db.execute(
            select(CrawlPage).where(CrawlPage.crawl_id == crawl_id)
        )
        return list(result.scalars().all())
    
    async def get_by_url(self, crawl_id: UUID, normalized_url: str) -> Optional[CrawlPage]:
        """Get page by crawl ID and normalized URL."""
        result = await self.db.execute(
            select(CrawlPage).where(
                CrawlPage.crawl_id == crawl_id,
                CrawlPage.normalized_url == normalized_url,
            )
        )
        return result.scalar_one_or_none()
    
    async def update(self, crawl_page: CrawlPage) -> CrawlPage:
        """Update crawl page."""
        await self.db.flush()
        await self.db.refresh(crawl_page)
        return crawl_page
    
    async def delete(self, page_id: UUID) -> bool:
        """Delete crawl page."""
        crawl_page = await self.get_by_id(page_id)
        if crawl_page:
            await self.db.delete(crawl_page)
            return True
        return False