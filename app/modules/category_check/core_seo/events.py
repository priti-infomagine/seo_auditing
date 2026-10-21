"""
EventBus — Redis-backed event/publish system for pipeline events.

Redis is the single source of truth for counters, audit state, and event
streams. No in-memory counters or event storage — all writes and reads
go through Redis so both Celery worker processes and the web API process
observe the same state.

Keys:
    core_seo:events:{audit_id}         — Redis Stream (XADD, maxlen=5000, TTL=3600)
    core_seo:audit:{audit_id}:counters  — Hash of counter → int (TTL=3600)
    core_seo:audit:{audit_id}:state    — Hash of audit state fields (TTL=3600)
    core_seo:audit:{audit_id}:pages   — Hash of url → JSON page state (TTL=3600)
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.core.logger import logger

from .models import CoreSEOEventType, PipelineEvent

REDIS_TTL_SECONDS = 3600
_REDIS_PREFIX = "core_seo:audit"

# Default counters initialized when reset_counters is called.
_DEFAULT_COUNTERS = {
    "pages_discovered": 0,
    "pages_crawled": 0,
    "pages_parsed": 0,
    "pages_failed": 0,
    "rules_passed": 0,
    "rules_failed": 0,
    "rules_total": 0,
}

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
    """Read all fields from a Redis hash synchronously. Returns empty dict on failure."""
    client = _get_sync_redis()
    if client is None:
        return {}
    try:
        return client.hgetall(_redis_key(audit_id, suffix)) or {}
    except Exception as exc:
        logger.debug("EventBus Redis hgetall failed: %s", exc)
        return {}


def _redis_hget_sync(audit_id: str, suffix: str, field: str) -> str | None:
    """Read a single field from a Redis hash synchronously."""
    client = _get_sync_redis()
    if client is None:
        return None
    try:
        return client.hget(_redis_key(audit_id, suffix), field)
    except Exception as exc:
        logger.debug("EventBus Redis hget failed: %s", exc)
        return None


def _redis_hset_sync(audit_id: str, suffix: str, mapping: dict[str, Any]) -> None:
    """Set multiple fields in a Redis hash synchronously with TTL (best-effort).

    TTL is REDIS_TTL_SECONDS (3600 = 1 hour max) to ensure stale audit state
    auto-expires from Redis.
    """
    client = _get_sync_redis()
    if client is None:
        return
    try:
        flattened: dict[str, str] = {}
        for f, v in mapping.items():
            if isinstance(v, bool):
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


def _redis_hincrby_sync(audit_id: str, suffix: str, field: str, amount: int = 1) -> int:
    """Atomically increment a hash field in Redis (HINCRBY) with TTL refresh."""
    client = _get_sync_redis()
    if client is None:
        return 0
    try:
        key = _redis_key(audit_id, suffix)
        val = client.hincrby(key, field, amount)
        client.expire(key, REDIS_TTL_SECONDS)
        return val
    except Exception as exc:
        logger.debug("EventBus Redis hincrby failed: %s", exc)
        return 0


def _redis_delete_sync(audit_id: str, *suffixes: str) -> None:
    """Delete one or more Redis hash keys for an audit_id."""
    client = _get_sync_redis()
    if client is None:
        return
    try:
        keys = [f"{_REDIS_PREFIX}:{audit_id}"]
        for s in suffixes:
            keys.append(f"{_REDIS_PREFIX}:{audit_id}:{s}")
        client.delete(*keys)
    except Exception as exc:
        logger.debug("EventBus Redis delete failed: %s", exc)


class EventBus:
    """Redis-backed event bus for pipeline events.

    Redis is the single source of truth for counters, audit state, and the
    event stream. No in-memory counters or events are stored, ensuring
    cross-process visibility between Celery workers and the web API.
    """

    _subscribers: dict[str, list[Callable]] = {}

    # Event type → counter key (auto-incremented on emit)
    _COUNTER_KEY_MAP: dict[str, str] = {
        CoreSEOEventType.PAGE_DISCOVERED.value: "pages_discovered",
        CoreSEOEventType.PARSED.value: "pages_parsed",
        CoreSEOEventType.PAGE_COMPLETED.value: "pages_crawled",
    }

    def __init__(self, redis_client: Any | None = None):
        self._redis = redis_client  # kept for backwards-compat

    # ── Counter management ──────────────────────────────────────────

    @classmethod
    def reset_counters(cls, audit_id: str) -> None:
        """Initialize all counters to zero for an audit_id in Redis."""
        _redis_hset_sync(audit_id, "counters", {k: v for k, v in _DEFAULT_COUNTERS.items()})

    @classmethod
    def get_counters(cls, audit_id: str) -> dict[str, int]:
        """Read counters from the Redis hash directly."""
        raw = _redis_hgetall_sync(audit_id, "counters")
        if raw:
            return {k: int(v) if v else 0 for k, v in raw.items()}
        return dict(_DEFAULT_COUNTERS)

    @classmethod
    def increment(cls, audit_id: str, key: str, amount: int = 1) -> int:
        """Atomically increment a counter in Redis via HINCRBY."""
        return _redis_hincrby_sync(audit_id, "counters", key, amount)

    # ── Audit state management ────────────────────────────────────────

    @classmethod
    def set_audit_state(cls, audit_id: str, **fields: Any) -> None:
        """Write audit state fields to the Redis state hash with TTL."""
        _redis_hset_sync(audit_id, "state", fields)

    @classmethod
    def get_audit_state(cls, audit_id: str) -> dict[str, Any]:
        """Read audit state from the Redis state hash."""
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
    def get_state(cls, audit_id: str) -> dict[str, Any]:
        """Alias for get_audit_state."""
        return cls.get_audit_state(audit_id)

    @classmethod
    def clear_audit_state(cls, audit_id: str) -> None:
        """Remove all Redis state for an audit_id (counters, state, pages, events)."""
        _redis_delete_sync(audit_id, "counters", "state", "pages")
        client = _get_sync_redis()
        if client is not None:
            try:
                client.delete(f"core_seo:events:{audit_id}")
            except Exception as exc:
                logger.debug("EventBus Redis stream delete failed: %s", exc)

    # ── Page state management ────────────────────────────────────────

    @classmethod
    def set_page_state(cls, audit_id: str, url: str, state: dict[str, Any]) -> None:
        """Store a page's state in the Redis pages hash (url → JSON)."""
        _redis_hset_sync(audit_id, "pages", {url: json.dumps(state, default=str)})

    @classmethod
    def get_page_state(cls, audit_id: str, url: str) -> dict[str, Any]:
        """Read a single page's state from the Redis pages hash."""
        raw = _redis_hget_sync(audit_id, "pages", url)
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    @classmethod
    def get_all_page_states(cls, audit_id: str) -> dict[str, dict[str, Any]]:
        """Read all page states from the Redis pages hash."""
        raw = _redis_hgetall_sync(audit_id, "pages")
        states: dict[str, dict[str, Any]] = {}
        for url, json_str in raw.items():
            try:
                states[url] = json.loads(json_str) if json_str else {}
            except (json.JSONDecodeError, TypeError):
                states[url] = {}
        return states

    # ── Subscriber management (in-process only) ──────────────────────

    def subscribe(self, audit_id: str, callback: Callable[[PipelineEvent], None]) -> None:
        """Register a callback for all events of a given audit_id (in-process only)."""
        self._subscribers.setdefault(audit_id, []).append(callback)

    def subscribe_all(self, callback: Callable[[PipelineEvent], None]) -> None:
        """Register a callback for events of any audit_id (in-process only)."""
        self._subscribers.setdefault("__all__", []).append(callback)

    def unsubscribe(self, audit_id: str, callback: Callable[[PipelineEvent], None]) -> None:
        """Remove a previously-registered callback."""
        subs = self._subscribers.get(audit_id, [])
        if callback in subs:
            subs.remove(callback)

    # ── Event emission ───────────────────────────────────────────────

    def emit(
        self,
        event_type: CoreSEOEventType,
        audit_id: str,
        url: str = "",
        data: dict[str, Any] | None = None,
    ) -> PipelineEvent:
        """Emit an event: write to Redis stream and increment counters.

        Counters are incremented via HINCRBY for cross-process atomicity.
        """
        event_data = data or {}
        if not url and event_data.get("url"):
            url = event_data["url"]

        event = PipelineEvent(
            event_type=event_type.value if isinstance(event_type, CoreSEOEventType) else str(event_type),
            audit_id=audit_id,
            url=url,
            data=event_data,
        )

        et = event.event_type

        # Auto-increment counters based on event type
        counter_key = self._COUNTER_KEY_MAP.get(et)
        if counter_key:
            self.increment(audit_id, counter_key)

        # PAGE_FAILED increments ONLY pages_failed (not pages_crawled)
        if et == CoreSEOEventType.PAGE_FAILED.value:
            self.increment(audit_id, "pages_failed")

        # RULE_CHECKED: increment rules_passed or rules_failed based on result
        if et == CoreSEOEventType.RULE_CHECKED.value:
            if event_data.get("passed"):
                self.increment(audit_id, "rules_passed")
            else:
                self.increment(audit_id, "rules_failed")
            self.increment(audit_id, "rules_total")

        # Mirror event to Redis stream
        self._emit_to_redis(event)

        # Dispatch to in-process subscribers
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

    # ── Event retrieval ───────────────────────────────────────────────

    @classmethod
    def get_events_for_audit(cls, audit_id: str) -> list[PipelineEvent]:
        """Retrieve all events for a given audit_id from the Redis stream."""
        events: list[PipelineEvent] = []
        client = _get_sync_redis()
        if client is None:
            return events
        try:
            stream_key = f"core_seo:events:{audit_id}"
            entries = client.xrange(stream_key, count=5000)
            for _id, fields in entries:
                raw = fields.get("event", "")
                if raw:
                    try:
                        evt_data = json.loads(raw)
                        events.append(PipelineEvent(
                            event_type=evt_data.get("event_type", ""),
                            audit_id=evt_data.get("audit_id", audit_id),
                            url=evt_data.get("url", ""),
                            timestamp=evt_data.get("timestamp", ""),
                            data=evt_data.get("data", {}),
                        ))
                    except (json.JSONDecodeError, TypeError):
                        pass
        except Exception as exc:
            logger.debug("EventBus Redis xrange failed: %s", exc)
        return events

    @classmethod
    def get_report_events(cls, audit_id: str) -> list[PipelineEvent]:
        """Return the event log for an audit (alias for get_events_for_audit)."""
        return cls.get_events_for_audit(audit_id)

    @classmethod
    def get_status(cls, audit_id: str, **extra: Any) -> dict[str, Any]:
        """Return a status dict for an audit_id from Redis counters + state."""
        counters = cls.get_counters(audit_id)
        state = cls.get_audit_state(audit_id)
        return {
            "audit_id": audit_id,
            **counters,
            **state,
            **extra,
        }

    # ── Internal dispatch / Redis ─────────────────────────────────────

    def _dispatch(self, event: PipelineEvent) -> None:
        """Dispatch event to registered in-process subscribers."""
        callbacks: list[Callable] = []
        callbacks.extend(self._subscribers.get("__all__", []))
        callbacks.extend(self._subscribers.get(event.audit_id, []))
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
        """Write an event to the Redis stream with maxlen and TTL."""
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
            client.xadd(stream_key, {"event": payload}, maxlen=5000)
            client.expire(stream_key, REDIS_TTL_SECONDS)
        except Exception as exc:
            logger.debug("EventBus Redis emit failed: %s", exc)


__all__ = [
    "REDIS_TTL_SECONDS",
    "CoreSEOEventType",
    "EventBus",
    "PipelineEvent",
]
