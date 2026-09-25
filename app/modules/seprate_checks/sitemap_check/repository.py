from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .model import SitemapCheck


class SitemapCheckRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, check: SitemapCheck) -> SitemapCheck:
        self.db.add(check)
        await self.db.flush()
        await self.db.refresh(check)
        return check

    async def get(self, check_id: UUID) -> Optional[SitemapCheck]:
        result = await self.db.execute(
            select(SitemapCheck).where(SitemapCheck.id == check_id)
        )
        return result.scalar_one_or_none()

    async def get_by_domain(self, domain: str) -> Optional[SitemapCheck]:
        result = await self.db.execute(
            select(SitemapCheck)
            .where(SitemapCheck.domain == domain)
            .order_by(SitemapCheck.created_at.desc())
        )
        return result.scalar_one_or_none()