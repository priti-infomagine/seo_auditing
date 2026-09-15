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

    async def get_by_audit_id(self, audit_id: UUID) -> Optional[CrawlJob]:
        """Get crawl job by audit_id.

        In this codebase CrawlJob.id **is** the audit_id (see analyze.py which
        creates CrawlJob(id=audit_id)).  The public report and chat endpoints
        receive the audit_id from CrawlResponse, so this is an alias that
        resolves the same UUID against CrawlJob.id.
        """
        result = await self.db.execute(
            select(CrawlJob).where(CrawlJob.id == audit_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_or_audit_id(self, key: UUID) -> Optional[CrawlJob]:
        """Resolve a crawl job by its audit_id (CrawlJob.id).

        Tries ``id`` first, falls back to ``get_by_audit_id``. Both lookups
        resolve the same column; the fallback exists so callers can use
        whichever key they have from CrawlResponse.
        """
        job = await self.get_by_id(key)
        if job is not None:
            return job
        return await self.get_by_audit_id(key)

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
