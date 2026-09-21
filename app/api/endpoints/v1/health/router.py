from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.core.logger import logger
from fastapi import APIRouter, HTTPException, status
router = APIRouter()


@router.get("")
async def health_check():
    """Health check endpoint."""
    try:
        logger.info("GET /health - Health check endpoint called")
        return {
            "status": "healthy",
            "service": settings.APP_NAME,
            "timestamp": utc_now().isoformat(),
        }
    except Exception as exc:
        logger.error(f"Health check failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Health check failed",
        )
