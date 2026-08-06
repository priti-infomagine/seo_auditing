"""
PageAsset repository - database operations for PageAsset model.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crawler.models.page_assets import PageAsset


class PageAssetRepository:
    """Repository for PageAsset database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, page_asset: PageAsset) -> PageAsset:
        """Create a new page asset."""
        self.db.add(page_asset)
        await self.db.flush()
        await self.db.refresh(page_asset)
        return page_asset

    async def create_batch(self, page_assets: List[PageAsset]) -> List[PageAsset]:
        """Create multiple page assets."""
        self.db.add_all(page_assets)
        await self.db.flush()
        for asset in page_assets:
            await self.db.refresh(asset)
        return page_assets

    async def get_by_page_id(self, page_id: UUID) -> List[PageAsset]:
        """Get all assets for a page."""
        result = await self.db.execute(
            select(PageAsset).where(PageAsset.page_id == page_id)
        )
        return list(result.scalars().all())

    async def delete_by_page_id(self, page_id: UUID) -> bool:
        """Delete all assets for a page."""
        assets = await self.get_by_page_id(page_id)
        for asset in assets:
            await self.db.delete(asset)
        return True
