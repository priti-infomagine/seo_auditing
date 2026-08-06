"""
CrawlStatistics repository - database operations for crawl statistics.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawler_models.crawl_jobs import CrawlJob
from app.models.crawler_models.crawl_pages import CrawlPage
from app.models.crawler_models.page_links import PageLink
from app.models.crawler_models.page_assets import PageAsset
from app.models.crawler_models.crawl_errors import CrawlError


class CrawlStatisticsRepository:
    """Repository for crawl statistics operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_crawl_stats(self, crawl_id: UUID) -> Optional[dict]:
        """
        Get comprehensive statistics for a crawl job.

        Aggregates counts across pages, links, assets, and errors tables.
        """
        result = await self.db.execute(
            select(CrawlJob).where(CrawlJob.id == crawl_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return None

        # Count pages for this crawl
        pages_result = await self.db.execute(
            select(func.count())
            .select_from(CrawlPage)
            .where(CrawlPage.crawl_id == crawl_id)
        )
        pages_count = pages_result.scalar_one()

        # Count links
        links_result = await self.db.execute(
            select(func.count())
            .select_from(PageLink)
            .join(CrawlPage, PageLink.page_id == CrawlPage.id)
            .where(CrawlPage.crawl_id == crawl_id)
        )
        links_count = links_result.scalar_one()

        # Count assets
        assets_result = await self.db.execute(
            select(func.count())
            .select_from(PageAsset)
            .join(CrawlPage, PageAsset.page_id == CrawlPage.id)
            .where(CrawlPage.crawl_id == crawl_id)
        )
        assets_count = assets_result.scalar_one()

        # Count errors
        errors_result = await self.db.execute(
            select(func.count())
            .select_from(CrawlError)
            .where(CrawlError.crawl_id == crawl_id)
        )
        errors_count = errors_result.scalar_one()

        # Count internal vs external links
        internal_links_result = await self.db.execute(
            select(func.count())
            .select_from(PageLink)
            .join(CrawlPage, PageLink.page_id == CrawlPage.id)
            .where(CrawlPage.crawl_id == crawl_id, PageLink.is_internal == True)
        )
        internal_links_count = internal_links_result.scalar_one()

        return {
            "crawl_id": crawl_id,
            "domain": job.domain,
            "status": job.status,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "duration_ms": job.duration_ms,
            "pages_crawled": pages_count,
            "total_links": links_count,
            "internal_links": internal_links_count,
            "external_links": links_count - internal_links_count,
            "total_assets": assets_count,
            "total_errors": errors_count,
        }
