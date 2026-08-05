"""
PageSnapshot repository - database operations for storing HTML snapshots.
"""
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.crawler_models.crawl_pages import CrawlPage


class PageSnapshotRepository:
    """Repository for page snapshot operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def save_snapshot(self, page_id: UUID, html_content: str) -> None:
        """Save HTML snapshot for a page."""
        page = await self.get_by_id(page_id)
        if page:
            # In a real implementation, you might have a separate snapshots table
            # For now, we'll store it as part of the page or in a separate storage
            # This is a placeholder for snapshot storage logic
            pass
    
    async def get_by_id(self, page_id: UUID) -> Optional[CrawlPage]:
        """Get page snapshot by page ID."""
        result = await self.db.execute(
            select(CrawlPage).where(CrawlPage.id == page_id)
        )
        return result.scalar_one_or_none()