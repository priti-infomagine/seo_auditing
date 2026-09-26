from typing import Optional, List, Dict, Any, Union
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .model import (
    SitemapCheck,
    SitemapCheckStatus,
    SitemapOverallStatus,
    SitemapSeverity,
)


def _val(enum_or_str: Any) -> Any:
    if hasattr(enum_or_str, "value"):
        return enum_or_str.value
    return enum_or_str


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

    async def update_progress(
        self,
        check_id: UUID,
        status: Union[SitemapCheckStatus, str],
        progress: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        values: Dict[str, Any] = {"status": _val(status)}
        if progress is not None:
            values["progress"] = progress
        if error is not None:
            values["error"] = error

        await self.db.execute(
            update(SitemapCheck)
            .where(SitemapCheck.id == check_id)
            .values(**values)
        )
        await self.db.flush()

    async def update_completed(
        self,
        check_id: UUID,
        overall_status: Union[SitemapOverallStatus, str],
        severity: Union[SitemapSeverity, str],
        summary: Dict[str, Any],
        sitemaps: List[Dict[str, Any]],
        findings: List[Dict[str, Any]],
        recommendations: List[Dict[str, Any]],
        report_markdown: str,
        cost_seconds: float,
    ) -> Optional[SitemapCheck]:
        await self.db.execute(
            update(SitemapCheck)
            .where(SitemapCheck.id == check_id)
            .values(
                status=_val(SitemapCheckStatus.COMPLETED),
                overall_status=_val(overall_status),
                severity=_val(severity),
                summary=summary,
                sitemaps=sitemaps,
                findings=findings,
                recommendations=recommendations,
                report_markdown=report_markdown,
                cost_seconds=cost_seconds,
                error=None,
            )
        )
        await self.db.flush()
        return await self.get(check_id)