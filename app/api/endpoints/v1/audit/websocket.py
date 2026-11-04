"""
WebSocket endpoint for real-time audit progress streaming.

Replicates the CoreSEO 4-phase pattern:
1. Wait for audit to appear in Redis (up to 30s timeout)
2. Catch-up: replay all historical events from Redis stream
3. Final snapshot: if completed, send final report
4. Live stream: XREAD BLOCK for new events with resume support
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse

from app.core.logger import logger
from app.core.config import settings
from app.modules.audit.events import AuditEventBus, AuditEventType

router = APIRouter()

# How long (seconds) the WebSocket handler will poll for audit state before
# giving up on a nonexistent audit_id. Overridable via env var.
_WS_WAIT_TIMEOUT = int(os.environ.get("AUDIT_WS_WAIT_TIMEOUT", "30"))


@router.websocket("/ws/{audit_id}")
async def audit_websocket(websocket: WebSocket, audit_id: str):
    """Real-time audit progress stream via WebSocket.

    Reads from Redis stream: audit:events:{audit_id}
    Supports resume via ?last_id=<redis_entry_id>
    Supports detail mode via ?detail=true for granular rule events
    """
    # Check feature flag
    if not settings.AUDIT_WS_ENABLED:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="WebSocket streaming disabled")
        return

    await websocket.accept()

    # Parse query parameters
    raw_query = websocket.scope.get("query_string", b"")
    query_params: dict[str, list[str]] = {}
    if isinstance(raw_query, bytes):
        raw_query = raw_query.decode("utf-8")
    if raw_query:
        from urllib.parse import parse_qs
        query_params = parse_qs(raw_query)

    last_id = query_params.get("last_id", [""])[0]
    detail_mode = query_params.get("detail", ["false"])[0].lower() == "true"

    # Establish Redis client (async for WebSocket handler)
    import redis.asyncio as redis_async

    try:
        async_client = redis_async.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        await async_client.ping()
    except Exception:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Redis unavailable")
        return

    stream_key = f"audit:events:{audit_id}"

    async def _send_json(obj: dict[str, Any]) -> bool:
        """Send a JSON object as WebSocket frame. Returns False if client disconnected."""
        try:
            await websocket.send_text(json.dumps(obj))
            return True
        except (WebSocketDisconnect, RuntimeError):
            return False

    async def _send_final() -> bool | None:
        """Send the final snapshot if a report is available in Redis state.

        Returns:
            True  — snapshot sent successfully.
            None  — report not ready yet.
            False — client disconnected mid-send.
        """
        state = await asyncio.to_thread(AuditEventBus.get_audit_state, audit_id)
        report = state.get("report")
        if report is not None:
            try:
                await websocket.send_text(
                    json.dumps({
                        "type": "final",
                        "audit_id": audit_id,
                        "summary": report.get("summary", {}),
                        "pages": report.get("pages", []),
                        "status": "completed",
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

    def _is_completed() -> bool:
        state = AuditEventBus.get_audit_state(audit_id)
        return state.get("status") == "completed"

    def _is_failed() -> bool:
        state = AuditEventBus.get_audit_state(audit_id)
        return state.get("status") == "failed"

    try:
        # --- Phase 1: Wait for the audit to appear in Redis ----------------
        state = await asyncio.to_thread(AuditEventBus.get_audit_state, audit_id)
        if not state:
            for _ in range(_WS_WAIT_TIMEOUT):
                await asyncio.sleep(1)
                state = await asyncio.to_thread(AuditEventBus.get_audit_state, audit_id)
                if state:
                    break
            if not state:
                await _safe_close(
                    code=status.WS_1000_NORMAL_CLOSURE,
                    reason="Audit not found or no data available",
                )
                return

        # --- Phase 2: Send catch-up events from Redis stream using last_id ---
        if last_id:
            # Resume from specific entry ID
            try:
                entries = await async_client.xrange(stream_key, min=last_id, count=10000)
            except Exception:
                entries = []
        else:
            # From start
            try:
                entries = await async_client.xrange(stream_key, count=10000)
            except Exception:
                entries = []

        for entry_id, fields in entries:
            raw = fields.get("event", "")
            if raw:
                try:
                    evt = json.loads(raw)
                    # Filter detail mode events if not in detail mode
                    if not detail_mode and evt.get("event_type") == "rule_checked":
                        continue

                    sent = await _send_json({
                        "type": "event",
                        "event_type": evt.get("event_type", ""),
                        "audit_id": evt.get("audit_id", audit_id),
                        "url": evt.get("url", ""),
                        "timestamp": evt.get("timestamp", ""),
                        "seq": evt.get("seq", 0),
                        "payload": evt.get("data", {}),
                        "category": _categorize_event(evt.get("event_type", "")),
                    })
                    if not sent:
                        return
                except (json.JSONDecodeError, TypeError):
                    pass

        # --- Phase 3: If completed, send the final snapshot ---
        if _is_completed():
            result = await _send_final()
            if result is True:
                await _safe_close()
                return
            if result is False:
                return

        # --- Phase 4: Live-stream new events using XREAD BLOCK ---
        # Use $ to read only new entries
        streams = {stream_key: "$"}
        while True:
            try:
                resp = await async_client.xread(
                    streams,
                    count=10,
                    block=5000,
                )
                if resp:
                    for stream_key_resp, entries in resp:
                        for entry_id, fields in entries:
                            raw = fields.get("event", "")
                            if raw:
                                try:
                                    evt = json.loads(raw)
                                    # Filter detail mode events if not in detail mode
                                    if not detail_mode and evt.get("event_type") == "rule_checked":
                                        continue

                                    if not await _send_json({
                                        "type": "event",
                                        "event_type": evt.get("event_type", ""),
                                        "audit_id": evt.get("audit_id", audit_id),
                                        "url": evt.get("url", ""),
                                        "timestamp": evt.get("timestamp", ""),
                                        "seq": evt.get("seq", 0),
                                        "payload": evt.get("data", {}),
                                        "category": _categorize_event(evt.get("event_type", "")),
                                    }):
                                        return
                                except (json.JSONDecodeError, TypeError):
                                    pass

                # Check if audit completed or failed
                if _is_completed():
                    result = await _send_final()
                    if result is True:
                        await _safe_close()
                        return
                    if result is False:
                        return

                if _is_failed():
                    await _send_json({
                        "type": "error",
                        "audit_id": audit_id,
                        "message": "Audit pipeline failed",
                        "code": "PIPELINE_FAILED",
                    })
                    await _safe_close(code=status.WS_1000_NORMAL_CLOSURE, reason="Audit failed")
                    return

            except json.JSONDecodeError:
                continue
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for audit_id=%s", audit_id)
    except Exception as exc:
        logger.warning("WebSocket handler error for %s: %s", audit_id, exc, exc_info=True)
        await _safe_close(code=status.WS_1011_INTERNAL_ERROR, reason=str(exc))
    finally:
        try:
            await async_client.close()
        except Exception:
            pass


@router.get("/ws/{audit_id}", include_in_schema=True)
async def audit_websocket_http_docs(audit_id: str):
    """WebSocket endpoint documentation (HTTP GET stub).

    The real-time event stream lives at the WebSocket endpoint:
        ws://host:port/api/v1/audit/ws/{audit_id}

    Query parameters:
        last_id  – Redis stream entry ID to resume from (default: from start)
        detail   – If true, emit granular RULE_CHECKED events (default: false)

    WebSocket message format (JSON, each on its own frame):
        {"type":"event","event_type":"<EVENT_TYPE>","audit_id":"...","url":"...","timestamp":"...","seq":N,"payload":{},"category":"..."}
        {"type":"final","audit_id":"...","summary":{...},"pages":[...],"status":"completed"}
        {"type":"error","audit_id":"...","message":"...","code":"..."}

    Event types you will receive:
        crawl_started, crawl_page_started, crawl_page_fetched, crawl_page_persisted,
        crawl_page_failed, crawl_complete,
        parse_started, parse_page_complete, parse_complete,
        evaluate_started, rule_batch_complete, evaluate_page_complete, evaluate_complete,
        score_started, score_complete,
        pipeline_started, pipeline_completed, pipeline_failed
    """
    return JSONResponse(
        
        content={"detail": "This is a WebSocket endpoint. Use a WebSocket client to connect."},
    )


def _categorize_event(event_type: str) -> str:
    """Categorize event type for frontend routing/filtering."""
    if event_type.startswith("crawl_"):
        return "crawl"
    if event_type.startswith("parse_"):
        return "parse"
    if event_type.startswith("evaluate_") or event_type == "rule_batch_complete":
        return "evaluate"
    if event_type.startswith("score_"):
        return "score"
    if event_type.startswith("pipeline_"):
        return "pipeline"
    return "other"


__all__ = ["router"]