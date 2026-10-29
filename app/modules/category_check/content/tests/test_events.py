"""Tests for the Content EventBus (Redis-backed, content: prefix namespace)."""
from __future__ import annotations

import json

import pytest

from app.modules.category_check.content.events import (
    REDIS_TTL_SECONDS,
    ContentEventBus,
)
from app.modules.category_check.content.events import _redis_key, _get_sync_redis
from app.modules.category_check.content.models import ContentEventType, ContentPipelineEvent


def _redis_available():
    client = _get_sync_redis()
    return client is not None


pytestmark = pytest.mark.skipif(
    not _redis_available(),
    reason="Redis not available on 127.0.0.1:6379",
)


class TestContentEventBusCounters:
    def test_reset_counters_sets_defaults(self):
        ContentEventBus.reset_counters("test-content-evt-1")
        counters = ContentEventBus.get_counters("test-content-evt-1")
        for key in ("pages_discovered", "pages_crawled", "pages_parsed", "pages_failed", "rules_passed", "rules_failed"):
            assert counters[key] == 0
        ContentEventBus.clear_audit_state("test-content-evt-1")

    def test_page_discovered_increments_counter(self):
        ContentEventBus.reset_counters("test-content-evt-2")
        bus = ContentEventBus()
        bus.emit(ContentEventType.PAGE_DISCOVERED, "test-content-evt-2", data={"url": "https://a.com"})
        bus.emit(ContentEventType.PAGE_DISCOVERED, "test-content-evt-2", data={"url": "https://b.com"})
        counters = ContentEventBus.get_counters("test-content-evt-2")
        assert counters["pages_discovered"] == 2
        ContentEventBus.clear_audit_state("test-content-evt-2")

    def test_page_failed_increments_only_pages_failed(self):
        ContentEventBus.reset_counters("test-content-evt-3")
        bus = ContentEventBus()
        bus.emit(ContentEventType.PAGE_FAILED, "test-content-evt-3", data={"url": "https://a.com", "error": "timeout"})
        counters = ContentEventBus.get_counters("test-content-evt-3")
        assert counters["pages_failed"] == 1
        assert counters["pages_crawled"] == 0
        ContentEventBus.clear_audit_state("test-content-evt-3")

    def test_rule_checked_passed_increments_rules_passed(self):
        ContentEventBus.reset_counters("test-content-evt-4")
        bus = ContentEventBus()
        bus.emit(ContentEventType.RULE_CHECKED, "test-content-evt-4", data={"rule_id": "r1", "passed": True})
        counters = ContentEventBus.get_counters("test-content-evt-4")
        assert counters["rules_passed"] == 1
        assert counters["rules_failed"] == 0
        assert counters["rules_total"] == 1
        ContentEventBus.clear_audit_state("test-content-evt-4")

    def test_rule_checked_failed_increments_rules_failed(self):
        ContentEventBus.reset_counters("test-content-evt-5")
        bus = ContentEventBus()
        bus.emit(ContentEventType.RULE_CHECKED, "test-content-evt-5", data={"rule_id": "r1", "passed": False})
        counters = ContentEventBus.get_counters("test-content-evt-5")
        assert counters["rules_passed"] == 0
        assert counters["rules_failed"] == 1
        ContentEventBus.clear_audit_state("test-content-evt-5")


class TestContentEventBusStream:
    def test_events_persisted_to_stream(self):
        bus = ContentEventBus()
        bus.emit(ContentEventType.PAGE_DISCOVERED, "test-content-stream-1", data={"url": "https://a.com"})
        bus.emit(ContentEventType.PAGE_STARTED, "test-content-stream-1", data={"url": "https://a.com"})

        events = ContentEventBus.get_events_for_audit("test-content-stream-1")
        assert len(events) == 2
        assert events[0].event_type == "page_discovered"
        assert events[1].event_type == "page_started"
        ContentEventBus.clear_audit_state("test-content-stream-1")

    def test_event_ordering_preserved(self):
        bus = ContentEventBus()
        for i in range(5):
            bus.emit(ContentEventType.PAGE_DISCOVERED, "test-content-order-1", data={"url": f"https://a{i}.com"})

        events = ContentEventBus.get_events_for_audit("test-content-order-1")
        assert len(events) == 5
        urls = [e.data.get("url") for e in events]
        assert urls == [f"https://a{i}.com" for i in range(5)]
        ContentEventBus.clear_audit_state("test-content-order-1")

    def test_get_events_empty_for_unknown(self):
        events = ContentEventBus.get_events_for_audit("nonexistent-content-stream")
        assert events == []


class TestContentEventBusTTL:
    def test_all_keys_have_ttl(self):
        ContentEventBus.set_audit_state("test-content-ttl-1", status="running", total_pages=5)
        ContentEventBus.reset_counters("test-content-ttl-1")
        bus = ContentEventBus()
        bus.emit(ContentEventType.PAGE_DISCOVERED, "test-content-ttl-1", data={"url": "https://a.com"})

        client = _get_sync_redis()
        assert client is not None
        assert client.ttl(_redis_key("test-content-ttl-1", "counters")) == REDIS_TTL_SECONDS
        assert client.ttl(_redis_key("test-content-ttl-1", "state")) == REDIS_TTL_SECONDS
        assert client.ttl(f"content:events:test-content-ttl-1") == REDIS_TTL_SECONDS
        ContentEventBus.clear_audit_state("test-content-ttl-1")

    def test_ttl_is_3600(self):
        assert REDIS_TTL_SECONDS == 3600


class TestContentEventBusIsolation:
    """Verify content events are isolated from core_seo events."""

    def test_content_stream_key_differs_from_core(self):
        ContentEventBus.reset_counters("test-isolation-1")
        from app.modules.category_check.core_seo.events import EventBus
        EventBus.reset_counters("test-isolation-1")

        content_bus = ContentEventBus()
        core_bus = EventBus()
        core_bus.emit(
            __import__(
                "app.modules.category_check.core_seo.models",
                fromlist=["CoreSEOEventType"],
            ).CoreSEOEventType.PAGE_DISCOVERED,
            "test-isolation-1",
            data={"url": "https://core.com"},
        )
        content_bus.emit(ContentEventType.PAGE_DISCOVERED, "test-isolation-1", data={"url": "https://content.com"})

        core_events = EventBus.get_events_for_audit("test-isolation-1")
        content_events = ContentEventBus.get_events_for_audit("test-isolation-1")

        assert len(core_events) == 1
        assert core_events[0].data.get("url") == "https://core.com"

        assert len(content_events) == 1
        assert content_events[0].data.get("url") == "https://content.com"

        EventBus.clear_audit_state("test-isolation-1")
        ContentEventBus.clear_audit_state("test-isolation-1")
