"""
Audit routes — aggregated router.

Mounts all audit sub-routers under their respective prefixes.
"""
from fastapi import APIRouter

from app.api.endpoints.v1.audit.audit import router as audit_router
from app.api.endpoints.v1.audit.analyze import router as analyze_router

router = APIRouter()

router.include_router(audit_router, prefix="")
router.include_router(analyze_router, prefix="")
