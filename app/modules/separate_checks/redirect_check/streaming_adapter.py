"""Streaming adapter: Redis pub/sub bridge for redirect check SSE events.

Extends ``RedisQueueScheduler`` with event publishing/subscribing so the
redirect check pipeline can stream per-URL results to SSE clients in real time.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.logger import logger
from app.modules.streaming_audit.config import STREAMING_AUDIT_REDIS_NAMESPACE
from app.modules.streaming_audit.services.redis_scheduler import RedisQueueScheduler


class StreamingRedirectAdapter(RedisQueueScheduler):
    """Redis pub/sub extension of RedisQueueScheduler for redirect check events."""

    def ns_events(self, audit_id: str) -> str:
        return f"{STREAMING_AUDIT_REDIS_NAMESPACE}:{audit_id}:events"

    def _events_list_key(self, audit_id: str) -> str:
        return f"{self.ns(audit_id)}:events_list"

    async def publish_event(
        self,
        audit_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """Publish a single SSE event to the audit's event channel.

        Also stores the event in a Redis list for SSE catch-up/reconnect.
        Falls back gracefully if Redis is unavailable.
        """
        payload = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            serialized = json.dumps(payload)
            await self.redis.publish(self.ns_events(audit_id), serialized)
            await self.redis.rpush(self._events_list_key(audit_id), serialized)
        except Exception as exc:
            logger.warning("StreamingRedirectAdapter: failed to publish event: %s", exc)

    async def get_stored_events(self, audit_id: str) -> list[dict[str, Any]]:
        """Retrieve all stored events for an audit run (for SSE catch-up)."""
        raw = await self.redis.lrange(self._events_list_key(audit_id), 0, -1)
        events: list[dict[str, Any]] = []
        for item in raw:
            try:
                events.append(json.loads(item))
            except (json.JSONDecodeError, TypeError):
                continue
        return events

    async def clear_event_store(self, audit_id: str) -> None:
        """Clear stored events for an audit run (called at start)."""
        await self.redis.delete(self._events_list_key(audit_id))

    async def close(self) -> None:
        await self.redis.aclose()
