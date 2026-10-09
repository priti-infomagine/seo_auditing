from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .model import BacklinkCheck


class BacklinkCheckRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, check: BacklinkCheck) -> BacklinkCheck:
        self.db.add(check)
        await self.db.commit()
        await self.db.refresh(check)
        return check

    async def get(self, check_id: UUID) -> Optional[BacklinkCheck]:
        result = await self.db.execute(
            select(BacklinkCheck).where(BacklinkCheck.id == check_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        target: Optional[str],
        limit: int,
        offset: int,
    ) -> tuple[list[BacklinkCheck], int]:
        query = select(BacklinkCheck)
        count_query = select(func.count()).select_from(BacklinkCheck)
        if target:
            query = query.where(BacklinkCheck.target == target)
            count_query = count_query.where(BacklinkCheck.target == target)

        checks = await self.db.execute(
            query.order_by(BacklinkCheck.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        total = await self.db.scalar(count_query)
        return list(checks.scalars().all()), total or 0
