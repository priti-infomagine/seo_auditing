"""Subscription repository - database operations for Subscription model."""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payment.models.subscriptions import Subscription
from app.modules.payment.schemas.subscription_schemas import SubscriptionCreate


class SubscriptionRepository:
    """Repository for Subscription database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: SubscriptionCreate) -> Subscription:
        """Create a new subscription."""
        subscription = Subscription(
            plan_id=data.plan_id,
            user_id=data.user_id,
            start_date=data.start_date,
            current_period_start=data.current_period_start,
            current_period_end=data.current_period_end,
            status="active",
            cancel_at_period_end=False,
        )
        self.db.add(subscription)
        await self.db.flush()
        await self.db.refresh(subscription)
        return subscription

    async def get_by_id(self, subscription_id: UUID) -> Optional[Subscription]:
        """Get subscription by ID."""
        result = await self.db.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: UUID) -> list[Subscription]:
        """Get all subscriptions for a user."""
        result = await self.db.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_by_plan_id(self, plan_id: UUID) -> list[Subscription]:
        """Get all subscriptions for a plan."""
        result = await self.db.execute(
            select(Subscription).where(Subscription.plan_id == plan_id)
        )
        return list(result.scalars().all())
