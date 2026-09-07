"""
PageResource repository - database operations for PageResource model.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crawler.models.page_resources import PageResource


class PageResourceRepository:
    """Repository for PageResource database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, resource: PageResource) -> PageResource:
        """Create a new page resource."""
        self.db.add(resource)
        await self.db.flush()
        await self.db.refresh(resource)
        return resource

    async def create_batch(self, resources: List[PageResource]) -> List[PageResource]:
        """Create multiple page resources."""
        self.db.add_all(resources)
        await self.db.flush()
        for resource in resources:
            await self.db.refresh(resource)
        return resources

    async def get_by_page_id(self, page_id: UUID) -> List[PageResource]:
        """Get all resources for a page."""
        result = await self.db.execute(
            select(PageResource).where(PageResource.page_id == page_id)
        )
        return list(result.scalars().all())

    async def delete_by_page_id(self, page_id: UUID) -> bool:
        """Delete all resources for a page."""
        resources = await self.get_by_page_id(page_id)
        for resource in resources:
            await self.db.delete(resource)
        return True
