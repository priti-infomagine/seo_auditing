from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .model import MetaCheck, MetaCheckStatus


def _value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


class MetaCheckRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, check: MetaCheck) -> MetaCheck:
        self.db.add(check)
        await self.db.flush()
        await self.db.refresh(check)
        return check

    async def get(self, check_id: UUID) -> Optional[MetaCheck]:
        result = await self.db.execute(
            select(MetaCheck).where(MetaCheck.id == check_id)
        )
        return result.scalar_one_or_none()

    async def update_progress(
        self,
        check_id: UUID,
        status: MetaCheckStatus | str,
        progress: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        values: dict[str, Any] = {"status": _value(status)}
        if progress is not None:
            values["progress"] = progress
        if error is not None:
            values["error"] = error
        await self.db.execute(
            update(MetaCheck).where(MetaCheck.id == check_id).values(**values)
        )
        await self.db.flush()

    async def update_completed(
        self,
        check_id: UUID,
        pages: list[dict],
        findings: list[dict],
        summary: dict,
        overall_status: str,
        severity: str,
        cost_seconds: float,
    ) -> None:
        await self.db.execute(
            update(MetaCheck)
            .where(MetaCheck.id == check_id)
            .values(
                status=MetaCheckStatus.COMPLETED.value,
                pages=pages,
                findings=findings,
                summary=summary,
                overall_status=overall_status,
                severity=severity,
                cost_seconds=cost_seconds,
                error=None,
            )
        )
        await self.db.flush()