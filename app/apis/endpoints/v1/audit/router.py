"""
Audit routes — aggregated router.

Mounts all audit sub-routers under their respective prefixes.
"""
from fastapi import APIRouter

from app.apis.endpoints.v1.audit.audit import router as audit_router

router = APIRouter()

router.include_router(audit_router, prefix="")