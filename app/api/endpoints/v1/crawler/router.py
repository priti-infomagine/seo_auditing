"""
Crawler routes — aggregated router.

Mounts all crawler sub-routers under their respective prefixes.
"""
from fastapi import APIRouter

from app.api.endpoints.v1.crawler.crawl import router as crawl_router
from app.api.endpoints.v1.crawler.status import router as status_router

router = APIRouter()

router.include_router(crawl_router, prefix="")
router.include_router(status_router, prefix="")