"""SSE event streaming for redirect check results.

Provides real-time streaming via Redis pub/sub with a chunked-polling
fallback for clients that don't support SSE or when the pub/sub
connection is lost.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.core.logger import logger
from app.modules.streaming_audit.config import STREAMING_AUDIT_REDIS_NAMESPACE


def _format_sse_event(event: dict[str, Any]) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(event)}\n\n"


async def _stored_events(
    redis: Redis,
    audit_id: str,
    last_id: int = 0,
) -> list[dict[str, Any]]:
    """Retrieve stored events from the redirect check event list (catch-up).

    Returns an empty list if Redis is unreachable or the key does not exist.
    """
    key = f"{STREAMING_AUDIT_REDIS_NAMESPACE}:{audit_id}:events_list"
    try:
        raw = await asyncio.wait_for(redis.lrange(key, last_id, -1), timeout=5.0)
    except (asyncio.TimeoutError, OSError, ResponseError) as exc:
        logger.debug("_stored_events: read error for audit_id=%s: %s", audit_id, exc)
        return []
    events: list[dict[str, Any]] = []
    for item in raw:
        try:
            events.append(json.loads(item))
        except (json.JSONDecodeError, TypeError):
            continue
    return events


async def sse_event_stream(
    audit_id: str,
    redis: Redis,
    poll_interval: float = 5.0,
    max_poll_failures: int = 60,
) -> AsyncIterator[str]:
    """Async generator yielding SSE-formatted events for a redirect check.

    Strategy:
    1. Emit a ``retry`` line so the client auto-reconnects.
    2. Send any stored catch-up events from Redis list.
    3. Subscribe to the Redis pub/sub channel for live events.
    4. If pub/sub yields no events, poll the StreamingAuditRun DB row +
       stored events as a fallback (chunked polling).
    5. On completion or error, emit a final ``close`` event.

    All Redis operations are guarded with timeouts so a transient
    connectivity issue degrades to the polling fallback rather than
    killing the stream.
    """
    pubsub = redis.pubsub()
    channel = f"{STREAMING_AUDIT_REDIS_NAMESPACE}:{audit_id}:events"
    processed_count = 0
    fallback_failures = 0

    yield "retry: 5000\n\n"

    try:
        catchup = await _stored_events(redis, audit_id)
        for event in catchup:
            processed_count += 1
            yield _format_sse_event(event)

        try:
            await asyncio.wait_for(pubsub.subscribe(channel), timeout=5.0)
        except (asyncio.TimeoutError, OSError, ResponseError) as exc:
            logger.warning("sse_event_stream: subscribe failed for audit_id=%s: %s", audit_id, exc)

        while True:
            # Use get_message with timeout for blocking wait (proper redis.asyncio API)
            try:
                message = await pubsub.get_message(timeout=1.0)
            except (asyncio.TimeoutError, OSError, ResponseError) as exc:
                logger.debug("sse_event_stream: get_message error for audit_id=%s: %s", audit_id, exc)
                message = None

            if message and message.get("type") == "message":
                try:
                    event = json.loads(message["data"])
                    processed_count += 1
                    yield _format_sse_event(event)

                    if event.get("event") == "completed":
                        yield _format_sse_event({"event": "close", "data": {"status": "completed"}})
                        return
                    elif event.get("event") == "discovery_complete":
                        event.get("data", {}).get("total_urls", 0)
                except (json.JSONDecodeError, TypeError):
                    continue

            fallback_events = await _stored_events(redis, audit_id, last_id=processed_count)
            if fallback_events:
                for event in fallback_events:
                    processed_count += 1
                    yield _format_sse_event(event)
                    if event.get("event") == "completed":
                        yield _format_sse_event({"event": "close", "data": {"status": "completed"}})
                        return

            if not fallback_events:
                fallback_failures += 1
                if fallback_failures >= max_poll_failures:
                    logger.warning("sse_event_stream: no events for audit_id=%s, stopping", audit_id)
                    yield _format_sse_event({"event": "close", "data": {"status": "idle"}})
                    return
                await asyncio.sleep(poll_interval)

    except asyncio.CancelledError:
        logger.info("sse_event_stream: client disconnected for audit_id=%s", audit_id)
        raise
    except Exception as exc:
        logger.error("sse_event_stream: error for audit_id=%s: %s", audit_id, exc)
        yield _format_sse_event({"event": "error", "data": {"error": str(exc)[:512]}})
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        except Exception:
            pass
