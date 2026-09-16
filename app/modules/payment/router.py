
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.payment.schemas.plan_schemas import PlanListResponse, PlanResponse
from app.modules.payment.services.plan_service import PlanService
from app.modules.payment.routers.subscriptions_router import router as subscription_router

router = APIRouter(tags=["Plans"])


def get_plan_service(db: AsyncSession = Depends(get_db)) -> PlanService:
    """Dependency that provides a PlanService instance."""
    return PlanService(db)


router.include_router(subscription_router, prefix="/subscriptions", tags=["Subscriptions"])


@router.get(
    "",
    response_model=PlanListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all plans",
    description=(
        "Returns a list of subscription plans. "
        "Public endpoint - no authentication required. "
        "Filter by is_active, plan_type. Supports pagination."
    ),
)
async def list_plans(
    is_active: Optional[bool] = Query(
        None,
        description="Filter by active status. None returns all, true returns only active.",
    ),
    plan_type: Optional[str] = Query(
        None,
        description="Filter by plan type (e.g., 'basic', 'pro', 'enterprise').",
    ),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of plans to return."),
    offset: int = Query(0, ge=0, description="Number of plans to skip."),
    service: PlanService = Depends(get_plan_service),
) -> PlanListResponse:
    """List all plans with optional filters."""
    return await service.list_plans(
        is_active=is_active,
        plan_type=plan_type,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{plan_id}",
    response_model=PlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Get plan by ID",
    description="Returns a single plan by its UUID. Public endpoint.",
)
async def get_plan_by_id(
    plan_id: UUID,
    service: PlanService = Depends(get_plan_service),
) -> PlanResponse:
    """Get a single plan by its UUID."""
    return await service.get_by_id(plan_id)


@router.get(
    "/code/{code}",
    response_model=PlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Get plan by code",
    description="Returns a single plan by its unique code (e.g., 'basic', 'pro'). Public endpoint.",
)
async def get_plan_by_code(
    code: str,
    service: PlanService = Depends(get_plan_service),
) -> PlanResponse:
    """Get a single plan by its code."""
    return await service.get_by_code(code)