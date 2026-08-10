"""
PageNetworkData repository - database operations for PageNetworkData model.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crawler.models.page_network_data import PageNetworkData


class PageNetworkDataRepository:
    """Repository for PageNetworkData database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: PageNetworkData) -> PageNetworkData:
        """Create a new PageNetworkData record."""
        self.db.add(data)
        await self.db.flush()
        await self.db.refresh(data)
        return data

    async def get_by_page_id(self, page_id: UUID) -> Optional[PageNetworkData]:
        """Get PageNetworkData by page ID."""
        result = await self.db.execute(
            select(PageNetworkData).where(PageNetworkData.page_id == page_id)
        )
        return result.scalar_one_or_none()

    async def update(self, data: PageNetworkData) -> PageNetworkData:
        """Update PageNetworkData."""
        await self.db.flush()
        await self.db.refresh(data)
        return data

    async def upsert(self, data: PageNetworkData) -> PageNetworkData:
        """Create or update PageNetworkData for a page_id."""
        existing = await self.get_by_page_id(data.page_id)
        if existing:
            for key, value in data.__dict__.items():
                if key not in ("id", "page_id", "created_at", "updated_at", "_sa_instance_state"):
                    setattr(existing, key, value)
            return await self.update(existing)
        return await self.create(data)
