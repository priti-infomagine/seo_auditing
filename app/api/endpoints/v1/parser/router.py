"""
Parser routes — aggregated router.

Mounts all parser sub-routers under their respective prefixes.
"""
from fastapi import APIRouter

from app.api.endpoints.v1.parser.parse import router as parse_router

router = APIRouter()

router.include_router(parse_router, prefix="")