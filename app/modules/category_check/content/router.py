"""
FastAPI router for the Content crawler pipeline.

Endpoints:
    POST /content/crawl           — start a content-only audit
    GET  /content/status/{id}     — poll content audit status
    GET  /content/report/{id}     — retrieve full content audit report

The shared WebSocket at /core-seo/ws/{id} handles dual-stream merging
for both core_seo and content events. The content router has its own
crawl/status/report endpoints for when content checks are run
independently.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.core.logger import logger
from app.core.redis import get_redis
from app.modules.separate_checks.sitemap_check.errors import (
    NO_SITEMAP_MESSAGE,
    NoSitemapAvailableError,
)
from .events import ContentEventBus
from .pipeline import ContentCrawlerService
from .schema import (
    ContentAuditConfig,
    ContentAuditReportResponse,
    ContentCrawlStartedResponse,
    ContentCrawlStatusResponse,
)
from .tasks import CELERY_AVAILABLE, run_content_audit

from app.modules.category_check.core_seo.page_discoverer import PageDiscoverer
from app.modules.category_check.core_seo.url_normalizer import URLNormalizer

router = APIRouter(prefix="/content")

content_router = router

_service: ContentCrawlerService | None = None


def get_service() -> ContentCrawlerService:
    global _service
    if _service is None:
        _service = ContentCrawlerService()
    return _service


@router.post("/crawl", response_model=ContentCrawlStartedResponse)
async def start_content_audit(config: ContentAuditConfig):
    """Start a Content-only audit.

    Dispatches as a Celery task when available, falls back to inline.
    """
    audit_id = str(uuid.uuid4())

    if CELERY_AVAILABLE:
        normalized = URLNormalizer.normalize_url(config.url)
        domain = URLNormalizer.get_domain(normalized)
        discoverer = PageDiscoverer()
        sitemap_urls = await discoverer._discover_sitemap_urls(
            normalized, domain, 100
        )
        if not sitemap_urls:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=NO_SITEMAP_MESSAGE,
            )

        redis_client = await get_redis()
        if redis_client:
            try:
                await redis_client.setex(
                    f"content:discovery:{audit_id}",
                    3600,
                    json.dumps(sitemap_urls),
                )
            except Exception:
                logger.debug("Failed to cache pre-flight sitemap URLs in Redis for content audit")

        await asyncio.to_thread(
            run_content_audit.delay,
            config.url,
            config.max_pages,
            audit_id=audit_id,
            require_sitemap=True,
        )
        logger.info("Content audit dispatched to Celery: audit_id=%s", audit_id)
    else:
        service = get_service()
        try:
            await service.start_audit(
                start_url=config.url,
                max_pages=config.max_pages,
                audit_id=audit_id,
                require_sitemap=True,
            )
        except NoSitemapAvailableError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=NO_SITEMAP_MESSAGE,
                headers={"X-Sitemap-Check": "not-found"},
            )
        logger.info("Content audit completed inline: audit_id=%s", audit_id)

    return ContentCrawlStartedResponse(
        audit_id=audit_id,
        status="started",
    )


@router.get("/status/{audit_id}", response_model=ContentCrawlStatusResponse)
async def get_content_audit_status(audit_id: str):
    """Poll content audit progress."""
    service = get_service()
    status_data = service.get_audit_status(audit_id)
    if status_data.get("status") == "unknown":
        raise HTTPException(status_code=404, detail=f"Content audit {audit_id} not found")

    events = ContentEventBus.get_events_for_audit(audit_id)
    status_data["events"] = [
        {
            "event_type": e.event_type,
            "url": e.url,
            "timestamp": e.timestamp,
            "payload": e.payload or e.data,
        }
        for e in events[-50:]
    ]
    return ContentCrawlStatusResponse(**status_data)


@router.get("/report/{audit_id}", response_model=ContentAuditReportResponse)
async def get_content_audit_report(audit_id: str):
    """Retrieve the full content audit report."""
    service = get_service()
    result = service.get_report(audit_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Content audit {audit_id} not found or still running")

    summary = result.summary or {}
    return ContentAuditReportResponse(
        audit_id=result.audit_id or audit_id,
        status=result.status,
        start_url=None,
        total_pages=summary.get("pages_total", 0),
        crawled_pages=summary.get("pages_done", 0),
        pages_done=summary.get("pages_done", 0),
        pages_failed=summary.get("pages_failed", 0),
        rules_passed=summary.get("rules_passed", 0),
        rules_failed=summary.get("rules_failed", 0),
        pass_percentage=summary.get("pass_percentage", 0.0),
        pages=result.pages,
        errors=[],
    )


__all__ = ["router", "content_router"]
