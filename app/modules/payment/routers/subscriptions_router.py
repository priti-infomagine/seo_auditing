"""
Subscription API Router.

Endpoints:
- POST /subscriptions/     - Create a subscription
- GET  /subscriptions/{id}  - Get a subscription by ID
- GET  /subscriptions/user/{user_id} - List subscriptions for a user
- GET  /subscriptions/plan/{plan_id} - List subscriptions for a plan
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.payment.schemas.subscription_schemas import (
    SubscriptionCreate,
    SubscriptionResponse,
)
from app.modules.payment.services.subscription_service import SubscriptionService

router = APIRouter(tags=["Subscriptions"])


def get_subscription_service(db: AsyncSession = Depends(get_db)) -> SubscriptionService:
    """Dependency that provides a SubscriptionService instance."""
    return SubscriptionService(db)


@router.post(
    "/",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create subscription",
    description="Create a new subscription for a user on a given plan.",
)
async def create_subscription(
    data: SubscriptionCreate,
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionResponse:
    """Create a new subscription."""
    return await service.create(data)


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get subscription by ID",
    description="Returns a single subscription by its UUID.",
)
async def get_subscription(
    subscription_id: UUID,
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionResponse:
    """Get a subscription by its UUID."""
    return await service.get_by_id(subscription_id)


@router.get(
    "/user/{user_id}",
    response_model=List[SubscriptionResponse],
    status_code=status.HTTP_200_OK,
    summary="List subscriptions for a user",
    description="Returns all subscriptions associated with a given user UUID.",
)
async def list_user_subscriptions(
    user_id: UUID,
    service: SubscriptionService = Depends(get_subscription_service),
) -> List[SubscriptionResponse]:
    """List all subscriptions for a user."""
    return await service.get_by_user_id(user_id)


@router.get(
    "/plan/{plan_id}",
    response_model=List[SubscriptionResponse],
    status_code=status.HTTP_200_OK,
    summary="List subscriptions for a plan",
    description="Returns all subscriptions associated with a given plan UUID.",
)
async def list_plan_subscriptions(
    plan_id: UUID,
    service: SubscriptionService = Depends(get_subscription_service),
) -> List[SubscriptionResponse]:
    """List all subscriptions for a plan."""
    return await service.get_by_plan_id(plan_id)
