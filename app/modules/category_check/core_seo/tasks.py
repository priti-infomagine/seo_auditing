"""
Celery/Celery-free tasks for the Core SEO pipeline.

Each task runs in its own process. Events are written directly to Redis
(no in-memory event collection), so the web API process can observe
real-time progress via Redis streams / WebSocket.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from app.core.logger import logger

from .config import CoreSEOConfig
from .constants import DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES
from .models import CrawlResult, PageScore
from .pipeline import CoreSEOCrawlerService  # imported here for test patching

try:
    from app.shared.tasks.celery_app import celery_app

    CELERY_AVAILABLE = True
except ImportError:
    celery_app = None
    CELERY_AVAILABLE = False


def _run_async(coro):
    """Run an async coroutine synchronously (for sync Celery tasks)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _serialize_page_score(
    page_score: PageScore,
    crawl_result: CrawlResult,
) -> dict[str, Any]:
    """Serialize a PageScore + CrawlResult for Celery return value."""
    return {
        "url": page_score.url,
        "status_code": crawl_result.status_code,
        "success": crawl_result.success,
        "error": crawl_result.error,
        "response_time_ms": crawl_result.response_time_ms,
        "passed": page_score.passed,
        "failed": page_score.failed,
        "total": page_score.total,
        "pass_percentage": page_score.pass_percentage,
        "rule_results": [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "passed": r.passed,
                "severity": r.severity,
                "message": r.message,
                "recommendation": r.recommendation,
                "details": r.details or {},
            }
            for r in page_score.rule_results
        ],
    }


def crawl_page_inline(
    url: str,
    audit_id: str,
    index: int = 0,
    total: int = 1,
) -> dict[str, Any]:
    """Run crawl + parse + rules for a single page in-line (no Celery).

    Emits events directly to Redis via EventBus — no in-memory collection.
    """
    service = CoreSEOCrawlerService()
    try:
        page_score, crawl_result = _run_async(
            service.process_page(url, audit_id, index=index, total=total)
        )
    except Exception as exc:
        logger.error("crawl_page_inline failed for %s: %s", url, exc)
        return {
            "url": url,
            "status_code": 0,
            "success": False,
            "error": str(exc),
            "response_time_ms": 0,
            "passed": 0,
            "failed": 0,
            "total": 0,
            "pass_percentage": 0.0,
            "rule_results": [],
        }
    return _serialize_page_score(page_score, crawl_result)


def run_audit_inline(
    start_url: str,
    max_pages: int | None = None,
    max_depth: int | None = None,
    audit_id: str | None = None,
    require_sitemap: bool = False,
) -> str:
    """Run a full audit in-line (no Celery).

    Pipeline events are emitted directly to Redis via EventBus.
    """
    # Retrieve pre-flight sitemap URLs from Redis (cached by the HTTP handler)
    # to avoid re-running sitemap discovery inside the worker.
    preflight_sitemap_urls: list[str] | None = None
    if audit_id:
        try:
            from .events import _get_sync_redis

            redis_client = _get_sync_redis()
            if redis_client:
                key = f"core_seo:discovery:{audit_id}"
                cached = redis_client.get(key)
                if cached:
                    preflight_sitemap_urls = json.loads(cached)
                redis_client.delete(key)
        except Exception:
            logger.debug(
                "Pre-flight sitemap cache miss for audit_id=%s; "
                "will discover in-worker",
                audit_id,
            )

    service = CoreSEOCrawlerService()
    audit_id = _run_async(
        service.start_audit(
            start_url=start_url,
            max_pages=max_pages,
            max_depth=max_depth,
            audit_id=audit_id,
            require_sitemap=require_sitemap,
            preflight_sitemap_urls=preflight_sitemap_urls,
        )
    )
    return audit_id


def finalize_audit_inline(audit_id: str) -> str:
    """Finalize an audit in-line: read counters + page states from Redis."""
    service = CoreSEOCrawlerService()
    _run_async(service.finalize_audit(audit_id))
    return audit_id


if CELERY_AVAILABLE:
    @celery_app.task(name="core_seo.crawl_page")
    def crawl_page_task(
        url: str,
        audit_id: str,
        index: int = 0,
        total: int = 1,
    ) -> dict[str, Any]:
        """Celery task: crawl + parse + evaluate rules for a single page.

        Emits events directly to Redis via EventBus — no in-memory collection.
        """
        return crawl_page_inline(url, audit_id, index=index, total=total)

    @celery_app.task(name="core_seo.finalize_audit")
    def finalize_audit_task(audit_id: str) -> str:
        """Celery task: finalize audit by reading Redis counters + page states."""
        return finalize_audit_inline(audit_id)

    @celery_app.task(name="core_seo.run_audit", bind=True, max_retries=3)
    def run_audit(self, start_url, max_pages=DEFAULT_MAX_PAGES, max_depth=DEFAULT_MAX_DEPTH, audit_id=None, require_sitemap=False):
        """Celery task: run a full Core SEO audit.

        Delegates to ``run_audit_inline`` — all events are emitted directly
        to Redis via EventBus, visible to the web API process in real time.
        """
        return run_audit_inline(
            start_url, max_pages=max_pages, max_depth=max_depth, audit_id=audit_id,
            require_sitemap=require_sitemap,
        )

else:
    def crawl_page_task(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return crawl_page_inline(*args, **kwargs)

    def finalize_audit_task(audit_id: str) -> str:
        return finalize_audit_inline(audit_id)

    def run_audit(*args: Any, **kwargs: Any) -> str:
        return run_audit_inline(*args, **kwargs)


__all__ = [
    "CELERY_AVAILABLE",
    "crawl_page_inline",
    "crawl_page_task",
    "finalize_audit_inline",
    "finalize_audit_task",
    "run_audit",
    "run_audit_inline",
]
