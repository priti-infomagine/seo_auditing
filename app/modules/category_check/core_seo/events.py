"""
EventBus — in-memory + Redis-backed event/publish system for pipeline events.

Counters and audit state are persisted to Redis so that both Celery worker
processes and the web API process can observe real-time progress for a given
audit_id.  In-memory counters remain the primary source within a single
process; Redis is used as the cross-process bridge.
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from app.core.datetime_utils import utc_now
from app.core.logger import logger

from .models import CoreSEOEventType, PipelineEvent

# Redis TTL: maximum 1 hour for all audit-related keys.
REDIS_TTL_SECONDS = 3600

_DEFAULT_COUNTERS: dict[str, dict[str, int]] = defaultdict(lambda: {
    "pages_discovered": 0,
    "pages_crawled": 0,
    "pages_parsed": 0,
    "pages_scored": 0,
    "pages_failed": 0,
    "rules_passed": 0,
    "rules_failed": 0,
    "rules_total": 0,
})

_REDIS_PREFIX = "core_seo:audit"

# Lazily-initialised *synchronous* Redis client usable from Celery tasks and
# sync FastAPI paths alike.
_redis_client: Any = None


def _get_sync_redis() -> Any:
    """Return a synchronous redis.Redis client or None if unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        from redis import Redis as SyncRedis
        from app.core.config import settings

        _redis_client = SyncRedis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=3,
            socket_connect_timeout=3,
        )
        return _redis_client
    except Exception:
        return None


def _redis_key(audit_id: str, suffix: str = "") -> str:
    base = f"{_REDIS_PREFIX}:{audit_id}"
    if suffix:
        base = f"{base}:{suffix}"
    return base


def _redis_hgetall_sync(audit_id: str, suffix: str) -> dict[str, str]:
    """Read a Redis hash synchronously. Returns empty dict on failure."""
    client = _get_sync_redis()
    if client is None:
        return {}
    try:
        return client.hgetall(_redis_key(audit_id, suffix)) or {}
    except Exception as exc:
        logger.debug("EventBus Redis hgetall failed: %s", exc)
        return {}


def _redis_hset_sync(audit_id: str, suffix: str, mapping: dict[str, Any]) -> None:
    """Set multiple fields in a Redis hash synchronously with TTL (best-effort).

    TTL is REDIS_TTL_SECONDS (3600 = 1 hour max) to ensure stale
    audit state auto-expires from Redis.
    """
    client = _get_sync_redis()
    if client is None:
        return
    try:
        flattened: dict[str, str] = {}
        for f, v in mapping.items():
            if isinstance(v, (bool,)):
                flattened[f] = str(v)
            elif isinstance(v, (str, int, float)):
                flattened[f] = str(v)
            else:
                flattened[f] = json.dumps(v, default=str)
        key = _redis_key(audit_id, suffix)
        client.hset(key, mapping=flattened)
        client.expire(key, REDIS_TTL_SECONDS)
    except Exception as exc:
        logger.debug("EventBus Redis hset failed: %s", exc)


class EventBus:
    """Async-safe in-memory event bus with per-audit_id counters.

    Counters are stored at the class level so they are shared across
    all EventBus instances within the same process (important for
    Celery workers that instantiate a fresh EventBus per task).

    For cross-process visibility (web API + Celery workers in separate
    processes), counters and audit state are also mirrored to Redis.
    """

    _counters: dict[str, dict[str, int]] = _DEFAULT_COUNTERS
    _subscribers: dict[str, list[Callable]] = defaultdict(list)
    _events: dict[str, list[PipelineEvent]] = defaultdict(list)
    _audit_state: dict[str, dict[str, Any]] = {}

    def __init__(self, redis_client: Any | None = None):
        self._redis = redis_client  # kept for backwards-compat; sync Redis used internally

    # ── Counter management ──────────────────────────────────────────

    @classmethod
    def _ensure_counters(cls, audit_id: str) -> None:
        if audit_id not in cls._counters:
            cls._counters[audit_id] = {
                "pages_discovered": 0,
                "pages_crawled": 0,
                "pages_parsed": 0,
                "pages_scored": 0,
                "rules_passed": 0,
                "rules_failed": 0,
                "rules_total": 0,
            }

    @classmethod
    def get_counters(cls, audit_id: str) -> dict[str, int]:
        """Get counters from in-memory first, fall back to Redis."""
        counters = cls._counters.get(audit_id)
        if counters is not None:
            return dict(counters)
        # Fall back to Redis (cross-process)
        raw = _redis_hgetall_sync(audit_id, "counters")
        if raw:
            return {k: int(v) if v else 0 for k, v in raw.items()}
        return {
            "pages_discovered": 0,
            "pages_crawled": 0,
            "pages_parsed": 0,
            "pages_scored": 0,
            "pages_failed": 0,
            "rules_passed": 0,
            "rules_failed": 0,
            "rules_total": 0,
        }

    @classmethod
    def reset_counters(cls, audit_id: str) -> None:
        cls._ensure_counters(audit_id)
        cls._counters[audit_id] = {
            "pages_discovered": 0,
            "pages_parsed": 0,
            "pages_crawled": 0,
            "pages_scored": 0,
            "pages_failed": 0,
            "rules_passed": 0,
            "rules_failed": 0,
            "rules_total": 0,
        }
        _redis_hset_sync(audit_id, "counters", cls._counters[audit_id])

    @classmethod
    def _increment(cls, audit_id: str, key: str, amount: int = 1) -> None:
        cls._ensure_counters(audit_id)
        cls._counters[audit_id][key] = cls._counters[audit_id].get(key, 0) + amount
        # Persist the updated counter value to Redis (cross-process visibility)
        _redis_hset_sync(audit_id, "counters", {key: cls._counters[audit_id][key]})

    @classmethod
    def set_audit_state(cls, audit_id: str, **fields: Any) -> None:
        """Update the audit state dict and mirror it to Redis."""
        if audit_id not in cls._audit_state:
            cls._audit_state[audit_id] = {}
        cls._audit_state[audit_id].update(fields)
        _redis_hset_sync(audit_id, "state", fields)

    @classmethod
    def get_audit_state(cls, audit_id: str) -> dict[str, Any]:
        """Return audit state from in-memory first, fall back to Redis."""
        state = cls._audit_state.get(audit_id)
        if state is not None:
            return dict(state)
        # Fall back to Redis
        raw = _redis_hgetall_sync(audit_id, "state")
        if raw:
            state: dict[str, Any] = {}
            for k, v in raw.items():
                try:
                    state[k] = json.loads(v) if v else None
                except (json.JSONDecodeError, TypeError):
                    state[k] = v
            return state
        return {}

    @classmethod
    def clear_audit_state(cls, audit_id: str) -> None:
        """Remove all in-memory and Redis state for an audit_id."""
        cls._counters.pop(audit_id, None)
        cls._events.pop(audit_id, None)
        cls._audit_state.pop(audit_id, None)
        client = _get_sync_redis()
        if client is not None:
            try:
                client.delete(_redis_key(audit_id, "counters"))
                client.delete(_redis_key(audit_id, "state"))
                client.delete(f"core_seo:events:{audit_id}")
            except Exception as exc:
                logger.debug("EventBus Redis clear failed: %s", exc)

    # ── Subscriber management ──────────────────────────────────────

    def subscribe(self, audit_id: str, callback: Callable[[PipelineEvent], None]) -> None:
        """Register a callback for all events of a given audit_id."""
        if audit_id not in self._subscribers:
            self._subscribers[audit_id] = []
        self._subscribers[audit_id].append(callback)

    def subscribe_all(self, callback: Callable[[PipelineEvent], None]) -> None:
        """Register a callback for events of any audit_id."""
        self._subscribers["__all__"].append(callback)

    def unsubscribe(self, audit_id: str, callback: Callable[[PipelineEvent], None]) -> None:
        subs = self._subscribers.get(audit_id, [])
        if callback in subs:
            subs.remove(callback)

    # ── Event emission ─────────────────────────────────────────────

    def emit(
        self,
        event_type: CoreSEOEventType,
        audit_id: str,
        url: str = "",
        data: dict[str, Any] | None = None,
    ) -> PipelineEvent:
        """Emit an event: call subscribers + update counters + store."""
        event = PipelineEvent(
            event_type=event_type.value if isinstance(event_type, CoreSEOEventType) else str(event_type),
            audit_id=audit_id,
            url=url,
            data=data or {},
        )

        key_map = {
            CoreSEOEventType.PAGE_DISCOVERED.value: "pages_discovered",
            CoreSEOEventType.PAGE_CRAWLED.value: "pages_crawled",
            CoreSEOEventType.PAGE_CRAWL_FAILED.value: "pages_crawled",
            CoreSEOEventType.PAGE_PARSED.value: "pages_parsed",
            CoreSEOEventType.PAGE_SCORED.value: "pages_scored",
        }
        key = key_map.get(event.event_type)
        if key:
            self._increment(audit_id, key)

        if event.event_type == CoreSEOEventType.PAGE_CRAWL_FAILED.value:
            self._increment(audit_id, "pages_failed")

        if data and "rules_passed" in data:
            self._increment(audit_id, "rules_passed", data["rules_passed"])
        if data and "rules_failed" in data:
            self._increment(audit_id, "rules_failed", data["rules_failed"])
        if data and "rules_total" in data:
            self._increment(audit_id, "rules_total", data["rules_total"])

        # Mirror event to Redis stream for cross-process consumption
        self._emit_to_redis(event)

        cls = EventBus
        if audit_id not in cls._events:
            cls._events[audit_id] = []
        cls._events[audit_id].append(event)

        self._dispatch(event)

        return event

    async def publish(self, event: PipelineEvent) -> None:
        """Async wrapper to emit a PipelineEvent (compatible with await)."""
        self.emit(
            event_type=event.event_type,
            audit_id=event.audit_id,
            url=event.url,
            data=event.payload or event.data,
        )

    @classmethod
    def get_events_for_audit(cls, audit_id: str) -> list[PipelineEvent]:
        """Retrieve all events for a given audit_id (in-memory + Redis stream)."""
        events = list(cls._events.get(audit_id, []))
        # If we have no in-memory events, try to read from Redis stream
        if not events:
            client = _get_sync_redis()
            if client is not None:
                try:
                    stream_key = f"core_seo:events:{audit_id}"
                    # Read all events from the stream
                    entries = client.xrange(stream_key, count=1000)
                    for _id, fields in entries:
                        raw = fields.get("event", "")
                        if raw:
                            try:
                                evt_data = json.loads(raw)
                                event = PipelineEvent(
                                    event_type=evt_data.get("event_type", ""),
                                    audit_id=evt_data.get("audit_id", audit_id),
                                    url=evt_data.get("url", ""),
                                    timestamp=evt_data.get("timestamp", ""),
                                    data=evt_data.get("data", {}),
                                )
                                events.append(event)
                            except (json.JSONDecodeError, TypeError):
                                pass
                except Exception as exc:
                    logger.debug("EventBus Redis xrange failed: %s", exc)
        return events

    @classmethod
    def add_events_for_audit(cls, audit_id: str, events: list[dict[str, Any]]) -> None:
        """Add events from serialized form (e.g., from Celery task results).

        Used when events are collected from parallel Celery workers and
        need to be merged into the central event store.
        """
        for evt_dict in events:
            event = PipelineEvent(
                event_type=evt_dict.get("event_type", ""),
                audit_id=audit_id,
                url=evt_dict.get("url", ""),
                timestamp=evt_dict.get("timestamp", ""),
                data=evt_dict.get("payload", evt_dict.get("data", {})),
            )
            cls._events[audit_id].append(event)
            key_map = {
                CoreSEOEventType.PAGE_DISCOVERED.value: "pages_discovered",
                CoreSEOEventType.PAGE_CRAWLED.value: "pages_crawled",
                CoreSEOEventType.PAGE_CRAWL_FAILED.value: "pages_crawled",
                CoreSEOEventType.PAGE_PARSED.value: "pages_parsed",
                CoreSEOEventType.PAGE_SCORED.value: "pages_scored",
            }
            key = key_map.get(event.event_type)
            if key:
                cls._increment(audit_id, key)
            if event.event_type == CoreSEOEventType.PAGE_CRAWL_FAILED.value:
                cls._increment(audit_id, "pages_failed")

    # ── Internal dispatch / Redis ───────────────────────────────────

    def _dispatch(self, event: PipelineEvent) -> None:
        callbacks: list[Callable] = []
        all_callbacks = self._subscribers.get("__all__", [])
        callbacks.extend(all_callbacks)
        specific = self._subscribers.get(event.audit_id, [])
        callbacks.extend(specific)

        for cb in callbacks:
            try:
                result = cb(event)
                if result is not None and hasattr(result, "__await__"):
                    import asyncio as _asyncio
                    try:
                        _asyncio.ensure_future(result)
                    except RuntimeError:
                        pass
            except Exception as exc:
                logger.warning("EventBus subscriber error: %s", exc)

    def _emit_to_redis(self, event: PipelineEvent) -> None:
        client = _get_sync_redis()
        if client is None:
            return
        try:
            payload = json.dumps(
                {
                    "event_type": event.event_type,
                    "audit_id": event.audit_id,
                    "url": event.url,
                    "timestamp": event.timestamp,
                    "data": event.data,
                },
                default=str,
            )
            stream_key = f"core_seo:events:{event.audit_id}"
            client.xadd(stream_key, {"event": payload}, maxlen=1000)
            client.expire(stream_key, REDIS_TTL_SECONDS)
        except Exception as exc:
            logger.debug("EventBus Redis emit failed: %s", exc)

    @classmethod
    def get_status(cls, audit_id: str, **extra: Any) -> dict[str, Any]:
        """Return a status dict for an audit_id from counters + Redis state."""
        counters = cls.get_counters(audit_id)
        state = cls.get_audit_state(audit_id)
        return {
            "audit_id": audit_id,
            **counters,
            **state,
            **extra,
        }


__all__ = ["REDIS_TTL_SECONDS", "CoreSEOEventType", "EventBus", "_utcnow_str"]
