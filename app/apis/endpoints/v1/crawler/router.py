"""
Crawler routes — aggregated router.

Mounts all crawler sub-routers under their respective prefixes.
"""
from fastapi import APIRouter

from app.apis.endpoints.v1.crawler.crawl import router as crawl_router

router = APIRouter()

router.include_router(crawl_router, prefix="")