"""
FastAPI router for the Core SEO crawler pipeline.

Endpoints:
    POST /core-seo/crawl           — start an audit
    GET  /core-seo/status/{id}     — poll audit status
    GET  /core-seo/report/{id}     — retrieve full audit report
    WS   /core-seo/ws/{id}         — real-time audit progress via WebSocket
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketException, status
from fastapi.responses import JSONResponse

from app.core.logger import logger

from .events import EventBus
from .models import CoreSEOEventType
from .page_discoverer import PageDiscoverer
from .pipeline import CoreSEOCrawlerService
from .schema import (
    AuditConfig,
    AuditReportResponse,
    CrawlStartedResponse,
    CrawlStatusResponse,
    RuleResultSchema,
)
from .tasks import CELERY_AVAILABLE, run_audit

router = APIRouter(prefix="/core-seo")

_service: CoreSEOCrawlerService | None = None


def get_service() -> CoreSEOCrawlerService:
    global _service
    if _service is None:
        _service = CoreSEOCrawlerService()
    return _service


@router.post("/crawl", response_model=CrawlStartedResponse)
async def start_audit(config: AuditConfig):
    """Start a Core SEO audit.

    Dispatches the audit as a Celery task so the worker logs
    'Task received' and processes it in the background. Falls back
    to inline execution when Celery is unavailable.
    """
    audit_id = str(uuid.uuid4())

    if CELERY_AVAILABLE:
        # Dispatch the Celery task; send_task/delay is blocking (Redis I/O),
        # so run it in a thread to avoid blocking the event loop.
        await asyncio.to_thread(
            run_audit.delay,
            config.url,
            config.max_pages,
            audit_id=audit_id,
        )
        logger.info("Core SEO audit dispatched to Celery: audit_id=%s", audit_id)
    else:
        # Fallback: run inline (no Celery worker available)
        service = get_service()
        await service.start_audit(
            start_url=config.url,
            max_pages=config.max_pages,
            audit_id=audit_id,
        )
        logger.info("Core SEO audit completed inline: audit_id=%s", audit_id)

    return CrawlStartedResponse(
        audit_id=audit_id,
        status="started",
    )


@router.get("/status/{audit_id}", response_model=CrawlStatusResponse)
async def get_audit_status(audit_id: str):
    """Poll audit progress."""
    service = get_service()
    status_data = service.get_audit_status(audit_id)
    if status_data.get("status") == "unknown":
        raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")

    events = EventBus.get_events_for_audit(audit_id)
    status_data["events"] = [
        {
            "event_type": e.event_type,
            "url": e.url,
            "timestamp": e.timestamp,
            "payload": e.payload or e.data,
        }
        for e in events[-50:]
    ]
    return CrawlStatusResponse(**status_data)


@router.get("/result/{audit_id}", response_model=AuditReportResponse)
async def get_audit_report(audit_id: str):
    """Retrieve the full audit report."""
    service = get_service()
    result = service.get_report(audit_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found or still running")

    summary = result.summary or {}
    return AuditReportResponse(
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


@router.get("/ws/{audit_id}", include_in_schema=True)
async def audit_websocket_http_docs(audit_id: str):
    """WebSocket endpoint documentation (HTTP GET stub).

    The real-time event stream lives at the WebSocket endpoint:
        ws://host:port/api/v1/category-check/core-seo/ws/{audit_id}

    Query parameters:
        last_id  – Redis stream entry ID to resume from (default: "0" for full catch-up).

    WebSocket message format (JSON, each on its own frame):
        {"type":"event","event_type":"<EVENT_TYPE>","audit_id":"...","url":"...","timestamp":"...","payload":{}}
        {"type":"final","audit_id":"...","summary":{...},"pages":[...]}

    Event types you will receive:
        audit_started, page_discovered, page_queued, page_started,
        fetch_started, rendered, parsed, rule_checked,
        page_completed, page_failed, audit_completed, audit_failed
    """
    raise HTTPException(
        status_code=426,
        detail="This is a WebSocket endpoint. Use a WebSocket client to connect.",
    )


@router.websocket("/ws/{audit_id}")
async def audit_websocket(websocket: WebSocket, audit_id: str):
    """Real-time audit progress stream via WebSocket.

    Clients can pass ``?last_id=<redis_stream_entry_id>`` to resume
    from a specific stream position. Falls back to DB snapshot when
    Redis data has expired.
    """
    await websocket.accept()

    # Accept optional last_id query param
    raw_query = websocket.scope.get("query_string", b"")
    query_params: dict[str, str] = {}
    if isinstance(raw_query, bytes):
        raw_query = raw_query.decode("utf-8")
    if raw_query:
        from urllib.parse import parse_qs
        parsed = parse_qs(raw_query)
        for k, v in parsed.items():
            query_params[k] = v[0] if v else ""

    last_id = query_params.get("last_id", "0")

    try:
        # Send existing events from stream for catch-up (always, even if completed)
        events = EventBus.get_events_for_audit(audit_id)
        for event in events:
            await websocket.send_text(
                json.dumps({
                    "type": "event",
                    "event_type": event.event_type,
                    "audit_id": event.audit_id,
                    "url": event.url,
                    "timestamp": event.timestamp,
                    "payload": event.payload or event.data,
                })
            )

        # Check if audit is completed
        state = EventBus.get_audit_state(audit_id)
        if state.get("status") == "completed":
            report = get_service().get_report(audit_id)
            if report is not None:
                await websocket.send_text(
                    json.dumps({
                        "type": "final",
                        "audit_id": audit_id,
                        "summary": report.summary,
                        "pages": report.pages,
                    })
                )
                await websocket.close()
                return

        # If no audit state exists and no events were sent, the audit_id
        # is unknown — close the connection instead of blocking forever.
        if not state and not events:
            await websocket.close(
                code=status.WS_1000_NORMAL_CLOSURE,
                reason="Audit not found or no data available",
            )
            return

        # Stream new events via Redis XREAD
        import redis

        try:
            from app.core.config import settings
            client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception:
            await websocket.close(code=1011, reason="Redis unavailable")
            return

        stream_key = f"core_seo:events:{audit_id}"

        # If no events exist yet and audit not completed, block-read
        while True:
            try:
                resp = client.xread(
                    {stream_key: last_id},
                    count=10,
                    block=5000,
                )
                if resp:
                    stream, entries = resp[0]
                    for entry_id, fields in entries:
                        last_id = entry_id
                        raw = fields.get("event", "")
                        if raw:
                            try:
                                evt = json.loads(raw)
                                await websocket.send_text(
                                    json.dumps({
                                        "type": "event",
                                        "event_type": evt.get("event_type", ""),
                                        "audit_id": evt.get("audit_id", audit_id),
                                        "url": evt.get("url", ""),
                                        "timestamp": evt.get("timestamp", ""),
                                        "payload": evt.get("data", {}),
                                    })
                                )
                            except (json.JSONDecodeError, TypeError):
                                pass

                # Check if audit completed
                state = EventBus.get_audit_state(audit_id)
                if state.get("status") == "completed":
                    report = get_service().get_report(audit_id)
                    if report is not None:
                        await websocket.send_text(
                            json.dumps({
                                "type": "final",
                                "audit_id": audit_id,
                                "summary": report.summary,
                                "pages": report.pages,
                            })
                        )
                        await websocket.close()
                        return
            except json.JSONDecodeError:
                continue
    except WebSocketException as exc:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason=exc.detail)
    except Exception as exc:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason=str(exc))


__all__ = ["router"]
