"""
Subscribe routes — aggregated router.
"""
from fastapi import APIRouter

from app.api.endpoints.v1.subscribe.subscribe import router as subscribe_router

router = APIRouter()

router.include_router(subscribe_router, prefix="", tags=["Subscribe"])