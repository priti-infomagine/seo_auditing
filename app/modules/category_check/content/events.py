"""
ContentEventBus — Redis-backed event/publish system for the Content pipeline.

Structurally mirrors core_seo's EventBus but uses a separate Redis key
namespace (``content:`` prefix) so content events and counters are
isolated from core_seo events while sharing the same audit_id.

Redis keys:
    content:events:{audit_id}         — Redis Stream (XADD, maxlen=5000, TTL=3600)
    content:audit:{audit_id}:counters  — Hash of counter → int (TTL=3600)
    content:audit:{audit_id}:state    — Hash of audit state fields (TTL=3600)
    content:audit:{audit_id}:pages   — Hash of url → JSON page state (TTL=3600)
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.core.logger import logger

from .models import ContentEventType, ContentPipelineEvent

REDIS_TTL_SECONDS = 3600
_CONTENT_REDIS_PREFIX = "content:audit"
_CONTENT_EVENTS_PREFIX = "content:events"

_DEFAULT_COUNTERS = {
    "pages_discovered": 0,
    "pages_crawled": 0,
    "pages_parsed": 0,
    "pages_failed": 0,
    "rules_passed": 0,
    "rules_failed": 0,
    "rules_total": 0,
}

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
    base = f"{_CONTENT_REDIS_PREFIX}:{audit_id}"
    if suffix:
        base = f"{base}:{suffix}"
    return base


def _redis_hgetall_sync(audit_id: str, suffix: str) -> dict[str, str]:
    client = _get_sync_redis()
    if client is None:
        return {}
    try:
        return client.hgetall(_redis_key(audit_id, suffix)) or {}
    except Exception as exc:
        logger.debug("ContentEventBus Redis hgetall failed: %s", exc)
        return {}


def _redis_hget_sync(audit_id: str, suffix: str, field: str) -> str | None:
    client = _get_sync_redis()
    if client is None:
        return None
    try:
        return client.hget(_redis_key(audit_id, suffix), field)
    except Exception as exc:
        logger.debug("ContentEventBus Redis hget failed: %s", exc)
        return None


def _redis_hset_sync(audit_id: str, suffix: str, mapping: dict[str, Any]) -> None:
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
        logger.debug("ContentEventBus Redis hset failed: %s", exc)


def _redis_hincrby_sync(audit_id: str, suffix: str, field: str, amount: int = 1) -> int:
    client = _get_sync_redis()
    if client is None:
        return 0
    try:
        key = _redis_key(audit_id, suffix)
        val = client.hincrby(key, field, amount)
        client.expire(key, REDIS_TTL_SECONDS)
        return val
    except Exception as exc:
        logger.debug("ContentEventBus Redis hincrby failed: %s", exc)
        return 0


def _redis_delete_sync(audit_id: str, *suffixes: str) -> None:
    client = _get_sync_redis()
    if client is None:
        return
    try:
        keys = [f"{_CONTENT_REDIS_PREFIX}:{audit_id}"]
        for s in suffixes:
            keys.append(f"{_CONTENT_REDIS_PREFIX}:{audit_id}:{s}")
        client.delete(*keys)
    except Exception as exc:
        logger.debug("ContentEventBus Redis delete failed: %s", exc)


class ContentEventBus:
    """Redis-backed event bus for content pipeline events.

    Mirrors core_seo's EventBus but uses the ``content:`` Redis namespace.
    Counters, state, pages, and events are fully isolated from core_seo.
    """

    _subscribers: dict[str, list[Callable]] = {}

    _COUNTER_KEY_MAP: dict[str, str] = {
        ContentEventType.PAGE_DISCOVERED.value: "pages_discovered",
        ContentEventType.PARSED.value: "pages_parsed",
        ContentEventType.PAGE_COMPLETED.value: "pages_crawled",
    }

    def __init__(self, redis_client: Any | None = None):
        self._redis = redis_client

    @classmethod
    def reset_counters(cls, audit_id: str) -> None:
        _redis_hset_sync(audit_id, "counters", {k: v for k, v in _DEFAULT_COUNTERS.items()})

    @classmethod
    def get_counters(cls, audit_id: str) -> dict[str, int]:
        raw = _redis_hgetall_sync(audit_id, "counters")
        if raw:
            return {k: int(v) if v else 0 for k, v in raw.items()}
        return dict(_DEFAULT_COUNTERS)

    @classmethod
    def increment(cls, audit_id: str, key: str, amount: int = 1) -> int:
        return _redis_hincrby_sync(audit_id, "counters", key, amount)

    @classmethod
    def set_audit_state(cls, audit_id: str, **fields: Any) -> None:
        _redis_hset_sync(audit_id, "state", fields)

    @classmethod
    def get_audit_state(cls, audit_id: str) -> dict[str, Any]:
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
        return cls.get_audit_state(audit_id)

    @classmethod
    def clear_audit_state(cls, audit_id: str) -> None:
        _redis_delete_sync(audit_id, "counters", "state", "pages")
        client = _get_sync_redis()
        if client is not None:
            try:
                client.delete(f"{_CONTENT_EVENTS_PREFIX}:{audit_id}")
            except Exception as exc:
                logger.debug("ContentEventBus Redis stream delete failed: %s", exc)

    @classmethod
    def set_page_state(cls, audit_id: str, url: str, state: dict[str, Any]) -> None:
        _redis_hset_sync(audit_id, "pages", {url: json.dumps(state, default=str)})

    @classmethod
    def get_page_state(cls, audit_id: str, url: str) -> dict[str, Any]:
        raw = _redis_hget_sync(audit_id, "pages", url)
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    @classmethod
    def get_all_page_states(cls, audit_id: str) -> dict[str, dict[str, Any]]:
        raw = _redis_hgetall_sync(audit_id, "pages")
        states: dict[str, dict[str, Any]] = {}
        for url, json_str in raw.items():
            try:
                states[url] = json.loads(json_str) if json_str else {}
            except (json.JSONDecodeError, TypeError):
                states[url] = {}
        return states

    def subscribe(self, audit_id: str, callback: Callable[[ContentPipelineEvent], None]) -> None:
        self._subscribers.setdefault(audit_id, []).append(callback)

    def subscribe_all(self, callback: Callable[[ContentPipelineEvent], None]) -> None:
        self._subscribers.setdefault("__all__", []).append(callback)

    def unsubscribe(self, audit_id: str, callback: Callable[[ContentPipelineEvent], None]) -> None:
        subs = self._subscribers.get(audit_id, [])
        if callback in subs:
            subs.remove(callback)

    def emit(
        self,
        event_type: ContentEventType,
        audit_id: str,
        url: str = "",
        data: dict[str, Any] | None = None,
    ) -> ContentPipelineEvent:
        event_data = data or {}
        if not url and event_data.get("url"):
            url = event_data["url"]

        event = ContentPipelineEvent(
            event_type=event_type.value if isinstance(event_type, ContentEventType) else str(event_type),
            audit_id=audit_id,
            url=url,
            data=event_data,
        )

        et = event.event_type
        counter_key = self._COUNTER_KEY_MAP.get(et)
        if counter_key:
            self.increment(audit_id, counter_key)

        if et == ContentEventType.PAGE_FAILED.value:
            self.increment(audit_id, "pages_failed")

        if et == ContentEventType.RULE_CHECKED.value:
            if event_data.get("passed"):
                self.increment(audit_id, "rules_passed")
            else:
                self.increment(audit_id, "rules_failed")
            self.increment(audit_id, "rules_total")

        self._emit_to_redis(event)
        self._dispatch(event)

        # Print content check events to console for easy testing
        if et in (
            ContentEventType.RULE_CHECKED.value,
            ContentEventType.PAGE_COMPLETED.value,
            ContentEventType.PAGE_FAILED.value,
            ContentEventType.AUDIT_COMPLETED.value,
        ):
            rule_id = event_data.get("rule_id", "")
            passed = event_data.get("passed", "")
            msg = event_data.get("message", "")[:80]
            try:
                print(
                    f"[content] {et} | audit={audit_id[:8]} | url={url} "
                    f"| rule_id={rule_id} | passed={passed} | msg={msg}",
                    flush=True,
                )
            except Exception:
                # Ignore encoding errors in console output
                pass

        return event

    async def publish(self, event: ContentPipelineEvent) -> None:
        self.emit(
            event_type=event.event_type,
            audit_id=event.audit_id,
            url=event.url,
            data=event.payload or event.data,
        )

    @classmethod
    def get_events_for_audit(cls, audit_id: str) -> list[ContentPipelineEvent]:
        events: list[ContentPipelineEvent] = []
        client = _get_sync_redis()
        if client is None:
            return events
        try:
            stream_key = f"{_CONTENT_EVENTS_PREFIX}:{audit_id}"
            entries = client.xrange(stream_key, count=5000)
            for _id, fields in entries:
                raw = fields.get("event", "")
                if raw:
                    try:
                        evt_data = json.loads(raw)
                        events.append(ContentPipelineEvent(
                            event_type=evt_data.get("event_type", ""),
                            audit_id=evt_data.get("audit_id", audit_id),
                            url=evt_data.get("url", ""),
                            timestamp=evt_data.get("timestamp", ""),
                            data=evt_data.get("data", {}),
                        ))
                    except (json.JSONDecodeError, TypeError):
                        pass
        except Exception as exc:
            logger.debug("ContentEventBus Redis xrange failed: %s", exc)
        return events

    @classmethod
    def get_report_events(cls, audit_id: str) -> list[ContentPipelineEvent]:
        return cls.get_events_for_audit(audit_id)

    @classmethod
    def get_status(cls, audit_id: str, **extra: Any) -> dict[str, Any]:
        counters = cls.get_counters(audit_id)
        state = cls.get_audit_state(audit_id)
        return {
            "audit_id": audit_id,
            **counters,
            **state,
            **extra,
        }

    def _dispatch(self, event: ContentPipelineEvent) -> None:
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
                logger.warning("ContentEventBus subscriber error: %s", exc)

    def _emit_to_redis(self, event: ContentPipelineEvent) -> None:
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
            stream_key = f"{_CONTENT_EVENTS_PREFIX}:{event.audit_id}"
            client.xadd(stream_key, {"event": payload}, maxlen=5000)
            client.expire(stream_key, REDIS_TTL_SECONDS)
        except Exception as exc:
            logger.debug("ContentEventBus Redis emit failed: %s", exc)


__all__ = [
    "REDIS_TTL_SECONDS",
    "ContentEventBus",
    "ContentEventType",
    "ContentPipelineEvent",
]
