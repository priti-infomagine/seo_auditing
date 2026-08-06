"""
Auth module router.

Aggregates all auth sub-routers under their respective prefixes.
"""
from fastapi import APIRouter

from app.api.endpoints.v1.auth.router import router as auth_v1_router

router = APIRouter()

router.include_router(auth_v1_router, prefix="/v1", tags=["Auth"])

__all__ = ["router"]
