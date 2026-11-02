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

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, WebSocketException, status
from fastapi.responses import JSONResponse

from app.core.logger import logger
from app.core.redis import get_redis
from app.modules.separate_checks.sitemap_check.errors import (
    NO_SITEMAP_MESSAGE,
    NoSitemapAvailableError,
)
from .events import EventBus, REDIS_TTL_SECONDS
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
from .url_normalizer import URLNormalizer
from .tasks import CELERY_AVAILABLE, run_audit

router = APIRouter(prefix="/core-seo")

_service: CoreSEOCrawlerService | None = None

# How long (seconds) the WebSocket handler will poll for audit state before
# giving up on a nonexistent audit_id.  Overridable via the
# CORE_SEO_WS_WAIT_TIMEOUT env var for testing.
_WS_WAIT_TIMEOUT = int(__import__("os").environ.get("CORE_SEO_WS_WAIT_TIMEOUT", "30"))


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
        # --- Pre-flight sitemap check (fail fast before queueing) ---
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

        # Cache sitemap URLs in Redis for the worker to reuse
        redis_client = await get_redis()
        if redis_client:
            try:
                await redis_client.setex(
                    f"core_seo:discovery:{audit_id}",
                    3600,
                    json.dumps(sitemap_urls),
                )
            except Exception:
                logger.debug("Failed to cache pre-flight sitemap URLs in Redis")

        # Dispatch the Celery task; send_task/delay is blocking (Redis I/O),
        # so run it in a thread to avoid blocking the event loop.
        await asyncio.to_thread(
            run_audit.delay,
            config.url,
            config.max_pages,
            audit_id=audit_id,
            require_sitemap=True,
        )
        logger.info("Core SEO audit dispatched to Celery: audit_id=%s", audit_id)
    else:
        # Fallback: run inline (no Celery worker available)
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

    # Merge events from both core_seo and content Redis streams
    core_events = EventBus.get_events_for_audit(audit_id)
    from ..content.events import ContentEventBus
    content_events = ContentEventBus.get_events_for_audit(audit_id)

    # Interleave and sort by timestamp for a unified event timeline
    all_events = []
    for e in core_events:
        all_events.append({
            "event_type": e.event_type,
            "url": e.url,
            "timestamp": e.timestamp,
            "payload": e.payload or e.data,
            "category": "core_seo",
        })
    for e in content_events:
        all_events.append({
            "event_type": e.event_type,
            "url": e.url,
            "timestamp": e.timestamp,
            "payload": e.payload or e.data,
            "category": "content",
        })
    all_events.sort(key=lambda e: e["timestamp"])
    status_data["events"] = all_events[-50:]
    return CrawlStatusResponse(**status_data)


@router.get("/result/{audit_id}", response_model=AuditReportResponse)
async def get_audit_report(audit_id: str):
    """Retrieve the full audit report."""
    service = get_service()
    result = service.get_report(audit_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found or still running")

    summary = result.summary or {}
    content_info = summary.get("content_summary", {})
    # Get content_pages from the NormalizedResult (populated by finalize_audit)
    content_pages = getattr(result, "content_pages", []) or []
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
        content_pages=content_pages,
        errors=[],
        content_rules_passed=content_info.get("rules_passed", summary.get("content_rules_passed", 0)),
        content_rules_failed=content_info.get("rules_failed", summary.get("content_rules_failed", 0)),
        content_pass_percentage=content_info.get("pass_percentage", summary.get("content_pass_percentage", 0.0)),
    )


@router.get("/ws/{audit_id}", include_in_schema=True)
async def audit_websocket_http_docs(audit_id: str):
    """WebSocket endpoint documentation (HTTP GET stub).

    The real-time event stream lives at the WebSocket endpoint:
        ws://host:port/api/v1/category-check/core-seo/ws/{audit_id}

    Query parameters (all formats supported):
        Legacy:
            last_seq         – Core SEO event sequence number to resume from (default: 0).
            last_content_seq – Content event sequence number to resume from (default: 0).

        Single category (one pair):
            seq       – Sequence number to resume from.
            category  – "core-seo" or "content".

        Multiple categories (array format, recommended):
            seq[]      – Array of sequence numbers.
            category[] – Array of categories ("core-seo" | "content"), parallel to seq[].

    Examples:
        ?last_seq=43&last_content_seq=15
        ?seq=43&category=core-seo
        ?seq=15&category=content
        ?seq[]=43&category[]=core-seo&seq[]=15&category[]=content

    WebSocket message format (JSON, each on its own frame):
        {"type":"event","event_type":"<EVENT_TYPE>","audit_id":"...","url":"...","timestamp":"...","seq":N,"payload":{},"category":"core_seo|content"}
        {"type":"final","audit_id":"...","summary":{...},"pages":[...],"content_pages":[...]}

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

    Reads from BOTH Redis streams — core_seo:events:{audit_id} and
    content:events:{audit_id} — tagging each event with its ``category``
    so the frontend can route/filter.

    Clients can pass ``?last_seq=<core_seo_seq>&last_content_seq=<content_seq>``
    to resume from a specific sequence number for each category.
    Default is 0 (from start).

    The final snapshot is sent only after BOTH core_seo and content
    audits have completed.
    """
    await websocket.accept()

    # Accept optional sequence query params for resumption
    # Supported formats:
    #   1. Legacy: ?last_seq=43&last_content_seq=15
    #   2. Single pair: ?seq=43&category=core-seo
    #   3. Multiple pairs: ?seq[]=43&category[]=core-seo&seq[]=15&category[]=content
    raw_query = websocket.scope.get("query_string", b"")
    query_params: dict[str, list[str]] = {}
    if isinstance(raw_query, bytes):
        raw_query = raw_query.decode("utf-8")
    if raw_query:
        from urllib.parse import parse_qs
        query_params = parse_qs(raw_query)

    def _extract_leading_int(value: str) -> int:
        """Extract leading integer from a string (handles malformed params like '15 ?seq=43')."""
        import re
        match = re.match(r'^\s*(\d+)', value)
        return int(match.group(1)) if match else 0

    def _get_seq_for_category(category: str, default: int = 0) -> int:
        """Extract sequence number for a category from various param formats."""
        # Format 1: Legacy params
        if category == "core_seo":
            if "last_seq" in query_params:
                return _extract_leading_int(query_params["last_seq"][0])
        elif category == "content":
            if "last_content_seq" in query_params:
                return _extract_leading_int(query_params["last_content_seq"][0])

        # Format 2: Single pair (seq + category)
        if "seq" in query_params and "category" in query_params:
            if query_params["category"][0] == category:
                return _extract_leading_int(query_params["seq"][0])

        # Format 3: Array pairs (seq[] + category[])
        if "seq[]" in query_params and "category[]" in query_params:
            seqs = query_params["seq[]"]
            cats = query_params["category[]"]
            for i, cat in enumerate(cats):
                if cat == category and i < len(seqs):
                    return _extract_leading_int(seqs[i])

        return default

    # Use sequence numbers for resumption (default 0 = from start)
    last_core_seq = _get_seq_for_category("core_seo")
    last_content_seq = _get_seq_for_category("content")

    # Establish Redis client once — reused for all stream reads below.
    import redis

    try:
        from app.core.config import settings
        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        # Verify connectivity
        client.ping()
    except Exception:
        await websocket.close(code=1011, reason="Redis unavailable")
        return

    core_stream_key = f"core_seo:events:{audit_id}"
    content_stream_key = f"content:events:{audit_id}"

    async def _send_event(evt: dict, category: str = "core_seo") -> bool:
        """Send a single event dict as a JSON frame with category tag.
        Returns False if the client has disconnected."""
        try:
            await websocket.send_text(
                json.dumps({
                    "type": "event",
                    "event_type": evt.get("event_type", ""),
                    "audit_id": evt.get("audit_id", audit_id),
                    "url": evt.get("url", ""),
                    "timestamp": evt.get("timestamp", ""),
                    "seq": evt.get("seq", 0),
                    "payload": evt.get("data", {}),
                    "category": category,
                })
            )
            return True
        except (WebSocketDisconnect, RuntimeError):
            return False

    async def _send_final(audit_id: str):
        """Send the final snapshot if a report is available.

        Returns:
            True  — snapshot sent successfully.
            None  — report not ready yet.
            False — client disconnected mid-send.
        """
        report = get_service().get_report(audit_id)
        if report is not None:
            try:
                await websocket.send_text(
                    json.dumps({
                        "type": "final",
                        "audit_id": audit_id,
                        "summary": report.summary,
                        "pages": report.pages,
                        "content_pages": getattr(report, "content_pages", []),
                    })
                )
                return True
            except (WebSocketDisconnect, RuntimeError):
                return False
        return None

    async def _safe_close(**kwargs) -> None:
        """Close the WebSocket, ignoring errors if already closing."""
        try:
            await websocket.close(**kwargs)
        except (WebSocketDisconnect, RuntimeError):
            pass

    def _is_core_completed() -> bool:
        state = EventBus.get_audit_state(audit_id)
        return state.get("status") == "completed"

    def _is_content_completed() -> bool:
        from ..content.events import ContentEventBus
        state = ContentEventBus.get_audit_state(audit_id)
        return state.get("status") == "completed"

    try:
        # --- Phase 1: Wait for the audit to appear in Redis ----------------
        state = await asyncio.to_thread(EventBus.get_audit_state, audit_id)
        if not state:
            for _ in range(_WS_WAIT_TIMEOUT):
                await asyncio.sleep(1)
                state = await asyncio.to_thread(EventBus.get_audit_state, audit_id)
                if state:
                    break
            if not state:
                await _safe_close(
                    code=status.WS_1000_NORMAL_CLOSURE,
                    reason="Audit not found or no data available",
                )
                return

        # --- Phase 2: Send catch-up events from BOTH streams using sequence numbers ---
        core_events = await asyncio.to_thread(
            EventBus.get_events_for_audit_after_seq, audit_id, last_core_seq
        )
        from ..content.events import ContentEventBus
        content_events = await asyncio.to_thread(
            ContentEventBus.get_events_for_audit_after_seq, audit_id, last_content_seq
        )

        # Merge and sort by sequence number for interleaved delivery
        all_catchup: list[tuple[str, Any]] = []
        for e in core_events:
            all_catchup.append(("core_seo", e))
        for e in content_events:
            all_catchup.append(("content", e))
        all_catchup.sort(key=lambda pair: pair[1].seq)

        for category, event in all_catchup:
            sent = await _send_event({
                "event_type": event.event_type,
                "audit_id": event.audit_id,
                "url": event.url,
                "timestamp": event.timestamp,
                "seq": event.seq,
                "data": event.payload or event.data,
            }, category=category)
            if not sent:
                return

        # Update last_seq to latest received in catch-up
        if core_events:
            last_core_seq = core_events[-1].seq
        if content_events:
            last_content_seq = content_events[-1].seq

        # --- Phase 3: If both streams completed, send the final snapshot ----
        core_done = _is_core_completed()
        content_done = _is_content_completed()
        if core_done and content_done:
            result = await _send_final(audit_id)
            if result is True:
                await _safe_close()
                return
            if result is False:
                return

        # --- Phase 4: Live-stream new events from both streams using seq filtering ---
        # Use $ to read only new entries, then filter by seq
        streams = {core_stream_key: "$", content_stream_key: "$"}
        while True:
            try:
                resp = await asyncio.to_thread(
                    client.xread,
                    streams,
                    count=10,
                    block=5000,
                )
                if resp:
                    for stream_key, entries in resp:
                        category = "core_seo" if stream_key == core_stream_key else "content"
                        for entry_id, fields in entries:
                            raw = fields.get("event", "")
                            if raw:
                                try:
                                    evt = json.loads(raw)
                                    evt_seq = evt.get("seq", 0)

                                    # Skip if we already sent this seq (duplicate protection)
                                    if category == "core_seo" and evt_seq <= last_core_seq:
                                        continue
                                    if category == "content" and evt_seq <= last_content_seq:
                                        continue

                                    # Update last_seq
                                    if category == "core_seo":
                                        last_core_seq = evt_seq
                                    else:
                                        last_content_seq = evt_seq

                                    if not await _send_event({
                                        "event_type": evt.get("event_type", ""),
                                        "audit_id": evt.get("audit_id", audit_id),
                                        "url": evt.get("url", ""),
                                        "timestamp": evt.get("timestamp", ""),
                                        "seq": evt_seq,
                                        "data": evt.get("data", {}),
                                    }, category=category):
                                        return
                                except (json.JSONDecodeError, TypeError):
                                    pass

                # Check if both audits completed
                core_done = _is_core_completed()
                content_done = _is_content_completed()
                if core_done and content_done:
                    result = await _send_final(audit_id)
                    if result is True:
                        await _safe_close()
                        return
                    if result is False:
                        return
            except json.JSONDecodeError:
                continue
    except WebSocketException as exc:
        await _safe_close(code=status.WS_1011_INTERNAL_ERROR, reason=exc.detail)
    except Exception as exc:
        logger.warning("WebSocket handler error for %s: %s", audit_id, exc, exc_info=True)
        await _safe_close(code=status.WS_1011_INTERNAL_ERROR, reason=str(exc))


__all__ = ["router"]
