"""
POST /subscribe — Subscribe to newsletter.
"""
from fastapi import APIRouter, HTTPException, status

from app.core.logger import logger
from app.modules.subscribe.schemas.subscribe import SubscribeRequest, SubscribeResponse
from app.modules.subscribe.services.subscribe_service import SubscribeService

router = APIRouter()


@router.post(
    "/",
    response_model=SubscribeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subscribe to newsletter",
    responses={
        201: {"description": "Subscribed successfully"},
        409: {"description": "Email already subscribed"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    },
)
async def subscribe(body: SubscribeRequest) -> SubscribeResponse:
    """Subscribe an email to the newsletter."""
    logger.info("POST /subscribe - Subscription request received")
    try:
        service = SubscribeService()
        return await service.execute(body)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Subscription failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process subscription. Please try again later.",
        )