"""
PageSEOData repository - database operations for PageSEOData model.
"""
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crawler.models.page_seo_data import PageSEOData


class PageSEODataRepository:
    """Repository for PageSEOData database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, page_seo_data: PageSEOData) -> PageSEOData:
        """Create a new PageSEOData record."""
        self.db.add(page_seo_data)
        await self.db.flush()
        await self.db.refresh(page_seo_data)
        return page_seo_data

    async def get_by_page_ids(self, page_ids: List[UUID]) -> Dict[UUID, PageSEOData]:
        """
        Batch-fetch SEO data by page IDs in a single query.

        Returns a dict keyed by page_id for O(1) lookup, replacing per-page
        `get_by_page_id` loops (N+1) in the analysis pipeline.
        """
        if not page_ids:
            return {}
        out: Dict[UUID, PageSEOData] = {}
        for start in range(0, len(page_ids), 1000):
            batch = page_ids[start : start + 1000]
            result = await self.db.execute(
                select(PageSEOData).where(PageSEOData.page_id.in_(batch))
            )
            for row in result.scalars().all():
                out[row.page_id] = row
        return out

    async def get_by_page_id(self, page_id: UUID) -> Optional[PageSEOData]:
        """Get PageSEOData by page ID."""
        result = await self.db.execute(
            select(PageSEOData).where(PageSEOData.page_id == page_id)
        )
        return result.scalar_one_or_none()

    async def update(self, page_seo_data: PageSEOData) -> PageSEOData:
        """Update PageSEOData."""
        await self.db.flush()
        await self.db.refresh(page_seo_data)
        return page_seo_data

    async def upsert(self, page_seo_data: PageSEOData) -> PageSEOData:
        """Create or update PageSEOData for a page_id."""
        existing = await self.get_by_page_id(page_seo_data.page_id)
        if existing:
            for key, value in page_seo_data.__dict__.items():
                if key not in ("id", "page_id", "created_at", "updated_at", "_sa_instance_state"):
                    setattr(existing, key, value)
            return await self.update(existing)
        return await self.create(page_seo_data)
