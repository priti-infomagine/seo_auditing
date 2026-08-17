from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.core.logger import logger

router = APIRouter()


@router.get("")
async def health_check():
    """Health check endpoint."""
    try:
        logger.info("GET /health - Health check endpoint called")
        return {
            "status": "healthy",
            "service": settings.APP_NAME,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error(f"Health check failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Health check failed",
        )
