from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }