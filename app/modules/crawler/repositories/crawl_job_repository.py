"""
CrawlJob repository - database operations for CrawlJob model.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crawler.models.crawl_jobs import CrawlJob


class CrawlJobRepository:
    """Repository for CrawlJob database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, crawl_job: CrawlJob) -> CrawlJob:
        """Create a new crawl job."""
        self.db.add(crawl_job)
        await self.db.flush()
        await self.db.refresh(crawl_job)
        return crawl_job

    async def get_by_id(self, crawl_job_id: UUID) -> Optional[CrawlJob]:
        """Get crawl job by ID with config eagerly loaded."""
        result = await self.db.execute(
            select(CrawlJob).where(CrawlJob.id == crawl_job_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: UUID) -> list[CrawlJob]:
        """Get all crawl jobs for a user."""
        result = await self.db.execute(
            select(CrawlJob).where(CrawlJob.user_id == user_id)
        )
        return list(result.scalars().all())

    async def update(self, crawl_job: CrawlJob) -> CrawlJob:
        """Update crawl job."""
        await self.db.flush()
        await self.db.refresh(crawl_job)
        return crawl_job

    async def delete(self, crawl_job_id: UUID) -> bool:
        """Delete crawl job."""
        crawl_job = await self.get_by_id(crawl_job_id)
        if crawl_job:
            await self.db.delete(crawl_job)
            return True
        return False
