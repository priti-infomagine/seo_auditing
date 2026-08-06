"""
Crawler API Endpoints
=====================
Endpoints for web crawling operations.
"""

from .crawl import router as crawl_router

__all__ = ['crawl_router']