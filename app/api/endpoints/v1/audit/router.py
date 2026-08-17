"""
Audit routes — aggregated router.

Mounts all audit sub-routers under their respective prefixes.
"""
from fastapi import APIRouter

from app.api.endpoints.v1.audit.audit import router as audit_router
from app.api.endpoints.v1.audit.analyze import router as analyze_router
from app.api.endpoints.v1.audit.parse import router as parse_router
from app.api.endpoints.v1.audit.evaluate import router as evaluate_router
from app.api.endpoints.v1.audit.score import router as score_router
from app.api.endpoints.v1.audit.results import router as results_router

router = APIRouter()

router.include_router(audit_router, prefix="")
router.include_router(analyze_router, prefix="")
router.include_router(parse_router, prefix="")
router.include_router(evaluate_router, prefix="")
router.include_router(score_router, prefix="")
router.include_router(results_router, prefix="")
