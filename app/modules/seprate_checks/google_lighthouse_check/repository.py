"""
Lighthouse check repository — async DB operations for LighthousePageResult.

Uses AsyncSession + sqlalchemy.select(), matching the codebase pattern
(cf. app/modules/crawler/repositories/).
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .model import LighthousePageResult, Device, PageStatus


class LighthousePageResultRepository:
    """Async repository for LighthousePageResult database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_check_id_domain(
        self, check_id: UUID, domain: str
    ) -> list[LighthousePageResult]:
        """Get all lighthouse results for a check + domain."""
        result = await self.db.execute(
            select(LighthousePageResult).where(
                LighthousePageResult.check_id == check_id,
                LighthousePageResult.domain == domain,
            )
        )
        return list(result.scalars().all())

    async def get_by_check_id(self, check_id: UUID) -> list[LighthousePageResult]:
        """Get all lighthouse results for a check (across all domains)."""
        result = await self.db.execute(
            select(LighthousePageResult).where(
                LighthousePageResult.check_id == check_id
            )
        )
        return list(result.scalars().all())

    async def get_by_check_id_domain_url_device(
        self,
        check_id: UUID,
        domain: str,
        url: str,
        device: Device,
    ) -> Optional[LighthousePageResult]:
        """Get a single lighthouse result by composite key."""
        result = await self.db.execute(
            select(LighthousePageResult).where(
                LighthousePageResult.check_id == check_id,
                LighthousePageResult.domain == domain,
                LighthousePageResult.url == url,
                LighthousePageResult.device == device,
            )
        )
        return result.scalar_one_or_none()

    async def insert(
        self,
        check_id: UUID,
        domain: str,
        url: str,
        device: Device,
        status: PageStatus,
        reason: Optional[str] = None,
        performance_score: Optional[int] = None,
        seo_score: Optional[int] = None,
        fcp_ms: Optional[int] = None,
        lcp_ms: Optional[int] = None,
        tbt_ms: Optional[int] = None,
        cls: Optional[float] = None,
    ) -> LighthousePageResult:
        """Insert a single result (does NOT commit — caller manages transaction)."""
        result = LighthousePageResult(
            check_id=check_id,
            domain=domain,
            url=url,
            device=device,
            status=status,
            reason=reason,
            performance_score=performance_score,
            seo_score=seo_score,
            fcp_ms=fcp_ms,
            lcp_ms=lcp_ms,
            tbt_ms=tbt_ms,
            cls=cls,
        )
        self.db.add(result)
        return result

    async def insert_batch(
        self, results: list[LighthousePageResult]
    ) -> list[LighthousePageResult]:
        """Bulk-insert multiple results (does NOT commit)."""
        self.db.add_all(results)
        return results
