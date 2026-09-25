from fastapi import APIRouter

from app.api.endpoints.v1.auth.router import router as auth_router
from app.api.endpoints.v1.health.router import router as health_router
from app.api.endpoints.v1.crawler.router import router as crawler_router
from app.api.endpoints.v1.audit.router import router as audit_router
from app.api.endpoints.v1.parser.router import router as parser_router
from app.api.endpoints.v1.scorer.router import router as scorer_router
from app.api.endpoints.v1.config.router import router as config_router
from app.modules.chat.router import router as chat_router
from app.modules.audit.api import audit_detail_router
from app.modules.reports.router import router as reports_router
from app.modules.payment.router import router as payment_router
from app.modules.seprate_checks.google_lighthouse_check.router import (
    router as lighthouse_router,
)
from app.modules.seprate_checks.robots_check.router import (
    router as robots_router,
)
from app.modules.seprate_checks.sitemap_check.router import (
    router as sitemap_router,
)

router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["Auth"])
router.include_router(health_router, prefix="/health", tags=["Health"])
router.include_router(crawler_router, prefix="/crawler", tags=["Crawler"])
router.include_router(audit_router, prefix="/audit", tags=["Audit"])
router.include_router(audit_detail_router, prefix="/audits", tags=["Audit (Read)"])
router.include_router(parser_router, prefix="/parser", tags=["Parser"])
router.include_router(scorer_router, prefix="/scorer", tags=["Scorer"])
router.include_router(config_router, prefix="/config/ignore-patterns", tags=["Config"])
router.include_router(chat_router, prefix="/chat", tags=["Chat"])
router.include_router(reports_router, prefix="/reports", tags=["Reports"])
router.include_router(payment_router, prefix="/plans", tags=["Plans"])
router.include_router(lighthouse_router, prefix="/lighthouse", tags=["Lighthouse"])
router.include_router(robots_router, prefix="/robots", tags=["Robots"])
router.include_router(sitemap_router, prefix="/sitemap", tags=["Sitemap"])

__all__ = ["router"]