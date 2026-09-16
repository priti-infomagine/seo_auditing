"""Plan repository - database operations for Plan model."""
from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payment.models.plans import Plan


class PlanRepository:
    """Repository for Plan database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all(
        self,
        is_active: Optional[bool] = None,
        plan_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Plan], int]:
        """Get all plans with optional filters. Returns (plans, total_count)."""
        stmt = select(Plan)
        count_stmt = select(func.count(Plan.id))

        if is_active is not None:
            stmt = stmt.where(Plan.is_active == is_active)
            count_stmt = count_stmt.where(Plan.is_active == is_active)
        if plan_type is not None:
            stmt = stmt.where(Plan.plan_type == plan_type)
            count_stmt = count_stmt.where(Plan.plan_type == plan_type)

        stmt = stmt.order_by(Plan.price).limit(limit).offset(offset)

        plans_result = await self.db.execute(stmt)
        count_result = await self.db.execute(count_stmt)

        plans = list(plans_result.scalars().all())
        total = count_result.scalar_one()

        return plans, total

    async def get_by_id(self, plan_id: UUID) -> Optional[Plan]:
        """Get plan by ID."""
        result = await self.db.execute(
            select(Plan).where(Plan.id == plan_id)
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Optional[Plan]:
        """Get plan by code."""
        result = await self.db.execute(
            select(Plan).where(Plan.code == code)
        )
        return result.scalar_one_or_none()