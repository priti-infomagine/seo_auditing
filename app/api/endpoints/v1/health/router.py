from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.core.#loggger import #loggger
from fastapi import APIRouter, HTTPException, status
router = APIRouter()


@router.get("")
async def health_check():
    """Health check endpoint."""
    try:
        #loggger.info("GET /health - Health check endpoint called")
        return {
            "status": "healthy",
            "service": settings.APP_NAME,
            "timestamp": utc_now().isoformat(),
        }
    except Exception as exc:
        #loggger.error(f"Health check failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Health check failed",
        )
