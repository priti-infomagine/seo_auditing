"""
CrawlSiteData repository - database operations for CrawlSiteData model.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crawler.models.crawl_site_data import CrawlSiteData


class CrawlSiteDataRepository:
    """Repository for CrawlSiteData database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: CrawlSiteData) -> CrawlSiteData:
        """Create a new CrawlSiteData record."""
        self.db.add(data)
        await self.db.flush()
        await self.db.refresh(data)
        return data

    async def get_by_crawl_job_id(self, crawl_job_id: UUID) -> Optional[CrawlSiteData]:
        """Get CrawlSiteData by crawl job ID."""
        result = await self.db.execute(
            select(CrawlSiteData).where(CrawlSiteData.crawl_job_id == crawl_job_id)
        )
        return result.scalar_one_or_none()

    async def update(self, data: CrawlSiteData) -> CrawlSiteData:
        """Update CrawlSiteData."""
        await self.db.flush()
        await self.db.refresh(data)
        return data

    async def upsert(self, data: CrawlSiteData) -> CrawlSiteData:
        """Create or update CrawlSiteData for a crawl_job_id."""
        existing = await self.get_by_crawl_job_id(data.crawl_job_id)
        if existing:
            for key, value in data.__dict__.items():
                if key not in ("id", "crawl_job_id", "created_at", "updated_at", "_sa_instance_state"):
                    setattr(existing, key, value)
            return await self.update(existing)
        return await self.create(data)
