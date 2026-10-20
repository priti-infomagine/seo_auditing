"""
Async repository for the ``robot_check`` table.

Follows the *session-injected* pattern of
``google_lighthouse_check/repository.py``: the caller owns the transaction.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .model import FetchStatus, OverallStatus, RobotCheck, Severity


class RobotCheckRepository:
    """Async repository for RobotCheck database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, row: RobotCheck) -> RobotCheck:
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def get_latest_by_domain(self, domain: str) -> Optional[RobotCheck]:
        result = await self.db.execute(
            select(RobotCheck)
            .where(RobotCheck.domain == domain)
            .order_by(RobotCheck.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, row_id: UUID) -> Optional[RobotCheck]:
        result = await self.db.execute(
            select(RobotCheck).where(RobotCheck.id == row_id)
        )
        return result.scalar_one_or_none()
