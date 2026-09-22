from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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

    async def get_by_check_id(
        self, check_id: UUID
    ) -> list[LighthousePageResult]:
        """Get all lighthouse results for a check."""
        result = await self.db.execute(
            select(LighthousePageResult).where(
                LighthousePageResult.check_id == check_id
            )
        )
        return list(result.scalars().all())

    async def get_count_by_check_id(self, check_id: UUID) -> dict:
        """Aggregate pagespeed result counts for a check."""
        result = await self.db.execute(
            select(
                LighthousePageResult.status,
                func.count(LighthousePageResult.id),
            )
            .where(LighthousePageResult.check_id == check_id)
            .group_by(LighthousePageResult.status)
        )

        counts = {status.value: 0 for status in PageStatus}
        total = 0

        for status_enum, count in result.all():
            key = (
                status_enum.value
                if hasattr(status_enum, "value")
                else status_enum
            )
            counts[key] = count
            total += count

        counts["total"] = total
        return counts

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

    async def upsert(
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
        """Insert or update a Lighthouse result atomically.

        Does NOT commit. The caller owns the transaction.
        """

        stmt = pg_insert(LighthousePageResult).values(
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

        stmt = stmt.on_conflict_do_update(
            constraint="uq_check_url_device",
            set_={
                "domain": stmt.excluded.domain,
                "status": stmt.excluded.status,
                "reason": stmt.excluded.reason,
                "performance_score": stmt.excluded.performance_score,
                "seo_score": stmt.excluded.seo_score,
                "fcp_ms": stmt.excluded.fcp_ms,
                "lcp_ms": stmt.excluded.lcp_ms,
                "tbt_ms": stmt.excluded.tbt_ms,
                "cls": stmt.excluded.cls,
            },
        ).returning(LighthousePageResult)

        result = await self.db.execute(stmt)
        return result.scalar_one()

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
        """Insert a single result.

        Prefer upsert() for Celery task results because tasks may retry.
        """
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

