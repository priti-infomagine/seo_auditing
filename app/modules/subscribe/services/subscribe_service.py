"""
Service layer for newsletter subscription.
"""
import uuid
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.logger import logger
from app.core.database import async_session_factory
from app.modules.subscribe.models.subscriber import Subscriber
from app.modules.subscribe.schemas.subscribe import SubscribeRequest, SubscribeResponse
from app.modules.subscribe.utils.email_utils import send_subscription_confirmation
from fastapi import HTTPException, status


class SubscribeService:
    """Encapsulates subscription business logic."""

    async def execute(self, request: SubscribeRequest) -> SubscribeResponse:
        """Process subscription request."""
        email = str(request.email).lower()
        logger.info(f"Subscription request for: {email}")

        # Check for existing subscription
        async with async_session_factory() as db:
            existing = await db.execute(
                select(Subscriber).where(Subscriber.email == email)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This email is already subscribed."
                )

            # Create subscriber record
            subscriber = Subscriber(id=uuid.uuid4(), email=email)
            db.add(subscriber)
            try:
                await db.commit()
                await db.refresh(subscriber)
            except IntegrityError:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This email is already subscribed."
                )

        # Dispatch confirmation email (fire-and-forget)
        send_subscription_confirmation(email)

        return SubscribeResponse()