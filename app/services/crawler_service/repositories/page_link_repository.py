"""
PageLink repository - database operations for PageLink model.
"""
import sys
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.crawler_models.page_links import PageLink


class PageLinkRepository:
    """Repository for PageLink database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create(self, page_link: PageLink) -> PageLink:
        """Create a new page link."""
        self.db.add(page_link)
        await self.db.flush()
        await self.db.refresh(page_link)
        return page_link
    
    async def create_batch(self, page_links: List[PageLink]) -> List[PageLink]:
        """Create multiple page links."""
        self.db.add_all(page_links)
        await self.db.flush()
        return page_links
    
    async def get_by_page_id(self, page_id: UUID) -> List[PageLink]:
        """Get all links for a page."""
        result = await self.db.execute(
            select(PageLink).where(PageLink.page_id == page_id)
        )
        return list(result.scalars().all())
    
    async def delete_by_page_id(self, page_id: UUID) -> bool:
        """Delete all links for a page."""
        links = await self.get_by_page_id(page_id)
        for link in links:
            await self.db.delete(link)
        return True