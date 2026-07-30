"""
User routes — aggregated router.

Mounts all user sub-routers under their respective prefixes.
"""
from fastapi import APIRouter

from app.apis.endpoints.v1.user.get_profile import router as profile_router

router = APIRouter()

router.include_router(profile_router, prefix="")