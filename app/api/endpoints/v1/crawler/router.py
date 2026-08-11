"""
Crawler routes — aggregated router.

Mounts all crawler sub-routers under their respective prefixes.
"""
from fastapi import APIRouter

from app.api.endpoints.v1.crawler.crawl import router as crawl_router
from app.api.endpoints.v1.crawler.status import router as status_router
from app.api.endpoints.v1.crawler.test_crawl import router as test_crawl_router

router = APIRouter()

router.include_router(crawl_router, prefix="")
router.include_router(status_router, prefix="")
router.include_router(test_crawl_router, prefix="")