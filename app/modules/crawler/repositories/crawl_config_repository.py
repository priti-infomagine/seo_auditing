"""
CrawlConfig repository - database operations for CrawlConfig model.
"""
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.modules.crawler.models.crawl_config import CrawlConfig


class CrawlConfigRepository:
    """Repository for CrawlConfig database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create(self, crawl_config: CrawlConfig) -> CrawlConfig:
        """Create a new crawl config."""
        self.db.add(crawl_config)
        await self.db.flush()
        await self.db.refresh(crawl_config)
        return crawl_config
    
    async def get_by_id(self, crawl_config_id: UUID) -> Optional[CrawlConfig]:
        """Get crawl config by ID."""
        result = await self.db.execute(
            select(CrawlConfig).where(CrawlConfig.id == crawl_config_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_crawl_id(self, crawl_id: UUID) -> Optional[CrawlConfig]:
        """Get crawl config by crawl job ID."""
        result = await self.db.execute(
            select(CrawlConfig).where(CrawlConfig.crawl_id == crawl_id)
        )
        return result.scalar_one_or_none()
    
    async def update(self, crawl_config: CrawlConfig) -> CrawlConfig:
        """Update crawl config."""
        await self.db.flush()
        await self.db.refresh(crawl_config)
        return crawl_config