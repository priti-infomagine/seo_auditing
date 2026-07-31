from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import settings
from app.core.logger import logger

router = APIRouter()


@router.get("")
async def health_check():
    logger.info("GET /health - Health check endpoint called")
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
