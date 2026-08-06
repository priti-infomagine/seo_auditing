from fastapi import APIRouter

from app.api.endpoints.v1.auth.router import router as auth_router
from app.api.endpoints.v1.health.router import router as health_router
from app.api.endpoints.v1.user.router import router as user_router
from app.api.endpoints.v1.crawler.router import router as crawler_router
from app.api.endpoints.v1.parser.router import router as parser_router
from app.api.endpoints.v1.audit.router import router as audit_router
from app.api.endpoints.v1.scorer.router import router as scorer_router

router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["Auth"])
router.include_router(health_router, prefix="/health", tags=["Health"])
router.include_router(user_router, prefix="/user", tags=["User"])
router.include_router(crawler_router, prefix="/crawler", tags=["Crawler"])
router.include_router(parser_router, prefix="/parser", tags=["Parser"])
router.include_router(audit_router, prefix="/audit", tags=["Audit"])
router.include_router(scorer_router, prefix="/scorer", tags=["Scorer"])

__all__ = ["router"]