"""
FastAPI router for the Core SEO crawler pipeline.

Endpoints:
    POST /crawl           — start a new audit
    GET  /status/{audit_id} — get audit status (or wait for completion)
    GET  /report/{audit_id} — get the full normalized audit report
    GET  /rules            — list registered rules
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.core.logger import logger

from .pipeline import CoreSEOCrawlerService
from .schema import (
    AuditConfig,
    CrawlStartedResponse,
    CrawlStatusResponse,
)
from .tasks import run_audit as run_audit_task

router = APIRouter(
    prefix="/core-seo",
)

_service: CoreSEOCrawlerService | None = None


def get_service() -> CoreSEOCrawlerService:
    """Get or create the singleton CoreSEOCrawlerService."""
    global _service
    if _service is None:
        _service = CoreSEOCrawlerService()
    return _service


@router.post("/crawl", response_model=CrawlStartedResponse)
async def start_crawl(
    request: Request,
    config: AuditConfig,
) -> CrawlStartedResponse:
    """Start a new Core SEO audit for the given URL."""
    service = get_service()

    audit_id = config.audit_id or str(
        __import__("uuid").uuid4()
    )

    try:
        if run_audit_task is not None and hasattr(run_audit_task, "delay"):
            run_audit_task.delay(
                start_url=config.url,
                max_pages=config.max_pages,
                max_depth=config.max_depth,
                audit_id=audit_id,
            )
            logger.info("Audit %s dispatched to Celery", audit_id)
        else:
            asyncio.create_task(
                service.start_audit(
                    start_url=config.url,
                    max_pages=config.max_pages,
                    max_depth=config.max_depth,
                    audit_id=audit_id,
                )
            )
            logger.info("Audit %s started (inline)", audit_id)
    except Exception as exc:
        logger.error("Failed to start audit: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to start audit") from exc

    return CrawlStartedResponse(
        audit_id=audit_id,
        status="started",
    )


@router.get("/status/{audit_id}", response_model=CrawlStatusResponse)
async def get_crawl_status(
    request: Request,
    audit_id: str,
) -> CrawlStatusResponse:
    """Get the current status of a running or completed audit."""
    service = get_service()

    status = service.get_audit_status(audit_id)
    if not status.get("status"):
        raise HTTPException(status_code=404, detail="Audit not found")

    # Fetch recent events from EventBus (reads from Redis if cross-process)
    events = service.event_bus.get_events_for_audit(audit_id)
    status["events"] = [
        {
            "event_type": e.event_type,
            "audit_id": e.audit_id,
            "url": e.url,
            "timestamp": e.timestamp,
            "payload": e.payload or e.data,
        }
        for e in events
    ]

    return CrawlStatusResponse(**status)


@router.get("/report/{audit_id}", response_model=dict[str, Any])
async def get_report(
    request: Request,
    audit_id: str,
) -> dict[str, Any]:
    """Get the full normalized audit report for a completed audit."""
    service = get_service()

    normalized = service.get_report(audit_id)
    if normalized is None:
        raise HTTPException(
            status_code=404,
            detail="Audit report not found or not yet completed",
        )

    return {
        "audit_id": normalized.audit_id,
        "status": normalized.status,
        "summary": normalized.summary,
        "pages": normalized.pages,
        "events": normalized.events,
    }


@router.get("/rules", response_model=dict[str, Any])
async def list_rules(request: Request) -> dict[str, Any]:
    """List all registered SEO rules with their metadata."""
    service = get_service()
    registry = service.get_rule_registry()

    rules = []
    for rule in registry:
        rules.append({
            "rule_id": rule.rule_id,
            "name": rule.name,
            "category": rule.category,
            "description": rule.description,
            "weight": rule.weight,
            "tags": list(rule.tags),
        })

    return {
        "total_rules": len(rules),
        "rules": rules,
    }


__all__ = ["router"]
