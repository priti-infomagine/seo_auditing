"""Subscription service - business logic for subscription operations."""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payment.repositories.subscription_repository import SubscriptionRepository
from app.modules.payment.schemas.subscription_schemas import SubscriptionCreate, SubscriptionResponse


class SubscriptionService:
    """Service for subscription operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = SubscriptionRepository(db)

    async def create(self, data: SubscriptionCreate) -> SubscriptionResponse:
        """Create a new subscription."""
        subscription = await self.repo.create(data)
        await self.db.commit()
        await self.db.refresh(subscription)
        return SubscriptionResponse.model_validate(subscription)

    async def get_by_id(self, subscription_id: UUID) -> SubscriptionResponse:
        """Get subscription by ID. Raises 404 if not found."""
        subscription = await self.repo.get_by_id(subscription_id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subscription with id {subscription_id} not found",
            )
        return SubscriptionResponse.model_validate(subscription)

    async def get_by_user_id(self, user_id: UUID) -> list[SubscriptionResponse]:
        """Get all subscriptions for a user."""
        subscriptions = await self.repo.get_by_user_id(user_id)
        return [SubscriptionResponse.model_validate(s) for s in subscriptions]

    async def get_by_plan_id(self, plan_id: UUID) -> list[SubscriptionResponse]:
        """Get all subscriptions for a plan."""
        subscriptions = await self.repo.get_by_plan_id(plan_id)
        return [SubscriptionResponse.model_validate(s) for s in subscriptions]
