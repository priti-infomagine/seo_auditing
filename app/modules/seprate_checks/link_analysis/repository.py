"""Link analysis repository — persistence operations only.

No business logic, no network I/O.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID

from redis.asyncio import Redis

from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from .model import (
    LinkAnalysisCheck,
    LinkAnalysisCheckStatus,
    LinkAnalysisOverallStatus,
    LinkAnalysisSeverity,
    LinkFinding,
    FindingCategory,
    FindingType,
)


def _val(enum_or_str: Any) -> Any:
    if hasattr(enum_or_str, "value"):
        return enum_or_str.value
    return enum_or_str


class LinkAnalysisRepository:
    def __init__(self, db: AsyncSession, redis: Optional[Redis] = None):
        self.db = db
        self.redis = redis

    # -- Redis helpers --------------------------------------------------

    def _redis_key(self, check_id: UUID) -> str:
        return f"link_analysis:check:{check_id}"

    async def set_status(
        self,
        check_id: UUID,
        status: Union[LinkAnalysisCheckStatus, str],
        progress: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        if self.redis is None:
            return
        payload: Dict[str, Any] = {"status": _val(status)}
        if progress is not None:
            payload["progress"] = progress
        if error is not None:
            payload["error"] = error
        try:
            await self.redis.set(self._redis_key(check_id), json.dumps(payload), ex=3600)
        except Exception as exc:
            logger.warning("Failed to set Redis status for check %s: %s", check_id, exc)

    async def get_status(self, check_id: UUID) -> Optional[Dict[str, Any]]:
        if self.redis is None:
            return None
        try:
            raw = await self.redis.get(self._redis_key(check_id))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Failed to get Redis status for check %s: %s", check_id, exc)
            return None

    async def clear_status(self, check_id: UUID) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.delete(self._redis_key(check_id))
        except Exception as exc:
            logger.warning("Failed to clear Redis status for check %s: %s", check_id, exc)

    # -- DB: check master row ------------------------------------------

    async def create(self, check: LinkAnalysisCheck) -> LinkAnalysisCheck:
        self.db.add(check)
        await self.db.flush()
        await self.db.refresh(check)
        return check

    async def get(self, check_id: UUID) -> Optional[LinkAnalysisCheck]:
        result = await self.db.execute(
            select(LinkAnalysisCheck).where(LinkAnalysisCheck.id == check_id)
        )
        return result.scalar_one_or_none()

    async def get_completed(self, check_id: UUID) -> Optional[LinkAnalysisCheck]:
        """Fetch a check row with completed status."""
        check = await self.get(check_id)
        if check is None:
            return None
        return check

    async def update_progress(
        self,
        check_id: UUID,
        status: Union[LinkAnalysisCheckStatus, str],
        progress: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update DB status (and error) and mirror to Redis."""
        values: Dict[str, Any] = {"status": _val(status)}
        if progress is not None:
            values["progress"] = progress
        if error is not None:
            values["error"] = error

        await self.db.execute(
            update(LinkAnalysisCheck)
            .where(LinkAnalysisCheck.id == check_id)
            .values(**values)
        )
        await self.db.flush()
        await self.set_status(check_id, status, progress, error)

    async def mark_processing(
        self,
        check_id: UUID,
        progress: Optional[Dict[str, Any]] = None,
    ) -> None:
        await self.update_progress(
            check_id,
            LinkAnalysisCheckStatus.PROCESSING,
            progress=progress,
        )

    async def mark_completed(
        self,
        check_id: UUID,
        summary: Dict[str, Any],
        overall_status: Optional[Union[LinkAnalysisOverallStatus, str]] = None,
        severity: Optional[Union[LinkAnalysisSeverity, str]] = None,
        cost_seconds: Optional[float] = None,
        pages_crawled: Optional[int] = None,
        crawl_truncated: Optional[bool] = None,
    ) -> Optional[LinkAnalysisCheck]:
        values: Dict[str, Any] = {
            "status": _val(LinkAnalysisCheckStatus.COMPLETED),
            "summary": summary,
            "error": None,
        }
        if overall_status is not None:
            values["overall_status"] = _val(overall_status)
        if severity is not None:
            values["severity"] = _val(severity)
        if cost_seconds is not None:
            values["cost_seconds"] = cost_seconds
        if pages_crawled is not None:
            values["pages_crawled"] = pages_crawled
        if crawl_truncated is not None:
            values["crawl_truncated"] = crawl_truncated

        await self.db.execute(
            update(LinkAnalysisCheck)
            .where(LinkAnalysisCheck.id == check_id)
            .values(**values)
        )
        await self.db.flush()
        await self.set_status(check_id, LinkAnalysisCheckStatus.COMPLETED)
        return await self.get(check_id)

    async def mark_failed(self, check_id: UUID, error: str) -> None:
        await self.db.execute(
            update(LinkAnalysisCheck)
            .where(LinkAnalysisCheck.id == check_id)
            .values(
                status=_val(LinkAnalysisCheckStatus.FAILED),
                error=error,
            )
        )
        await self.db.flush()
        await self.set_status(
            check_id,
            LinkAnalysisCheckStatus.FAILED,
            error=error,
        )

    async def set_task_id(self, check_id: UUID, task_id: str) -> None:
        await self.db.execute(
            update(LinkAnalysisCheck)
            .where(LinkAnalysisCheck.id == check_id)
            .values(task_id=task_id)
        )
        await self.db.flush()

    # -- DB: link findings --------------------------------------------

    async def delete_findings(self, check_id: UUID) -> None:
        """Delete all findings for a check (for idempotent re-runs)."""
        await self.db.execute(
            delete(LinkFinding).where(LinkFinding.check_id == check_id)
        )
        await self.db.flush()

    async def add_findings(self, findings: List[LinkFinding]) -> None:
        if findings:
            self.db.add_all(findings)
            await self.db.flush()

    async def get_findings(
        self,
        check_id: UUID,
        category: Optional[Union[FindingCategory, str]] = None,
        finding_type: Optional[Union[FindingType, str]] = None,
        severity: Optional[Union[LinkAnalysisSeverity, str]] = None,
        search: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[LinkFinding]:
        stmt = select(LinkFinding).where(LinkFinding.check_id == check_id)
        if category is not None and str(category).strip():
            cat_val = _val(category)
            stmt = stmt.where(func.lower(LinkFinding.category) == str(cat_val).strip().lower())
        if finding_type is not None and str(finding_type).strip():
            type_val = _val(finding_type)
            stmt = stmt.where(func.lower(LinkFinding.type) == str(type_val).strip().lower())
        if severity is not None and str(severity).strip():
            sev_val = _val(severity)
            stmt = stmt.where(func.lower(LinkFinding.severity) == str(sev_val).strip().lower())
        if search is not None and search.strip():
            stmt = stmt.where(LinkFinding.target_url.ilike(f"%{search.strip()}%"))
        stmt = stmt.order_by(LinkFinding.created_at).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_findings(
        self,
        check_id: UUID,
        category: Optional[Union[FindingCategory, str]] = None,
        finding_type: Optional[Union[FindingType, str]] = None,
        severity: Optional[Union[LinkAnalysisSeverity, str]] = None,
        search: Optional[str] = None,
        is_standard: Optional[bool] = None,
    ) -> int:
        stmt = select(func.count()).select_from(LinkFinding).where(LinkFinding.check_id == check_id)
        if category is not None and str(category).strip():
            cat_val = _val(category)
            stmt = stmt.where(func.lower(LinkFinding.category) == str(cat_val).strip().lower())
        if finding_type is not None and str(finding_type).strip():
            type_val = _val(finding_type)
            stmt = stmt.where(func.lower(LinkFinding.type) == str(type_val).strip().lower())
        if severity is not None and str(severity).strip():
            sev_val = _val(severity)
            stmt = stmt.where(func.lower(LinkFinding.severity) == str(sev_val).strip().lower())
        if search is not None and search.strip():
            stmt = stmt.where(LinkFinding.target_url.ilike(f"%{search.strip()}%"))
        if is_standard is True:
            stmt = stmt.where(func.lower(LinkFinding.category) == FindingCategory.STANDARD.value)
        elif is_standard is False:
            stmt = stmt.where(func.lower(LinkFinding.category) == FindingCategory.OPTIMIZATION.value)
        result = await self.db.execute(stmt)
        return result.scalar_one() or 0

    async def total_finding_count(self, check_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(LinkFinding).where(LinkFinding.check_id == check_id)
        )
        return result.scalar_one() or 0

