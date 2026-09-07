"""
Parser API Endpoints
====================
Endpoints for parsing crawled website data.
"""

from .parse import router as parse_router

__all__ = ['parse_router']