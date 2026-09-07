"""Compact audit read layer (additive)."""

from app.modules.audit.api.audit_detail_routes import router as audit_detail_router

__all__ = ["audit_detail_router"]
