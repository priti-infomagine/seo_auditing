from fastapi import APIRouter

from app.api.endpoints.v1.auth.router import router as auth_router
from app.api.endpoints.v1.health.router import router as health_router
from app.api.endpoints.v1.crawler.router import router as crawler_router

router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["Auth"])
router.include_router(health_router, prefix="/health", tags=["Health"])
router.include_router(crawler_router, prefix="/crawler", tags=["Crawler"])

__all__ = ["router"]