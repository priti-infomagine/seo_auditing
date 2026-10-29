"""
Celery/Celery-free tasks for the Content pipeline.

Mirrors core_seo's tasks.py but for content checks. Content checks run
inline within CoreSEOCrawlerService.process_page() via ContentCrawlerService,
so these tasks are primarily for standalone content audit scenarios.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.logger import logger

from .pipeline import ContentCrawlerService

try:
    from app.shared.tasks.celery_app import celery_app

    CELERY_AVAILABLE = True
except ImportError:
    celery_app = None
    CELERY_AVAILABLE = False


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def run_content_audit_inline(
    start_url: str,
    max_pages: int | None = None,
    max_depth: int | None = None,
    audit_id: str | None = None,
    require_sitemap: bool = False,
) -> str:
    """Run a full Content audit in-line (no Celery).

    Pipeline events are emitted directly to Redis via ContentEventBus.
    """
    service = ContentCrawlerService()
    audit_id = _run_async(
        service.start_audit(
            start_url=start_url,
            max_pages=max_pages,
            max_depth=max_depth,
            audit_id=audit_id,
            require_sitemap=require_sitemap,
        )
    )
    return audit_id


def finalize_content_audit_inline(audit_id: str) -> str:
    """Finalize a content audit in-line: read counters + page states from Redis."""
    service = ContentCrawlerService()
    _run_async(service.finalize_audit(audit_id))
    return audit_id


if CELERY_AVAILABLE:
    @celery_app.task(name="content.run_audit")
    def run_content_audit(start_url, max_pages=10, max_depth=3, audit_id=None, require_sitemap=False):
        return run_content_audit_inline(
            start_url, max_pages=max_pages, max_depth=max_depth,
            audit_id=audit_id, require_sitemap=require_sitemap,
        )

    @celery_app.task(name="content.finalize_audit")
    def finalize_content_audit_task(audit_id: str) -> str:
        return finalize_content_audit_inline(audit_id)

else:
    def run_content_audit(*args: Any, **kwargs: Any) -> str:
        return run_content_audit_inline(*args, **kwargs)

    def finalize_content_audit_task(audit_id: str) -> str:
        return finalize_content_audit_inline(audit_id)


__all__ = [
    "CELERY_AVAILABLE",
    "run_content_audit",
    "run_content_audit_inline",
    "finalize_content_audit_inline",
    "finalize_content_audit_task",
]
