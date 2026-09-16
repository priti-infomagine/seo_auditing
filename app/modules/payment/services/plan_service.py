"""Plan service - business logic for plan operations."""
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payment.repositories.plan_repository import PlanRepository
from app.modules.payment.schemas.plan_schemas import PlanListResponse, PlanResponse
from app.modules.payment.models.plans import Plan


class PlanService:
    """Service for plan operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PlanRepository(db)

    async def list_plans(
        self,
        is_active: Optional[bool] = None,
        plan_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PlanListResponse:
        """List plans with optional filters."""
        plans, total = await self.repo.get_all(
            is_active=is_active,
            plan_type=plan_type,
            limit=limit,
            offset=offset,
        )

        # Convert to response models
        plan_responses = [
            PlanResponse.model_validate(plan) for plan in plans
        ]

        return PlanListResponse(
            plans=plan_responses,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_by_id(self, plan_id: UUID) -> PlanResponse:
        """Get plan by ID."""
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan with id {plan_id} not found",
            )
        return PlanResponse.model_validate(plan)

    async def get_by_code(self, code: str) -> PlanResponse:
        """Get plan by code."""
        plan = await self.repo.get_by_code(code)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan with code '{code}' not found",
            )
        return PlanResponse.model_validate(plan)