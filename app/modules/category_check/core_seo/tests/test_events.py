"""Tests for the Redis-first EventBus implementation."""
from __future__ import annotations

import json

import pytest

from app.modules.category_check.core_seo.events import (
    REDIS_TTL_SECONDS,
    EventBus,
)
from app.modules.category_check.core_seo.events import _redis_key, _get_sync_redis
from app.modules.category_check.core_seo.models import CoreSEOEventType, PipelineEvent


def _redis_available():
    client = _get_sync_redis()
    return client is not None


pytestmark = pytest.mark.skipif(
    not _redis_available(),
    reason="Redis not available on 127.0.0.1:6379",
)


class TestEventBusCounters:
    """Verify counter increments on Redis via HINCRBY."""

    def test_reset_counters_sets_defaults(self):
        EventBus.reset_counters("test-evt-1")
        counters = EventBus.get_counters("test-evt-1")
        for key in ("pages_discovered", "pages_crawled", "pages_parsed", "pages_failed", "rules_passed", "rules_failed"):
            assert counters[key] == 0
        EventBus.clear_audit_state("test-evt-1")

    def test_page_discovered_increments_counter(self):
        EventBus.reset_counters("test-evt-2")
        bus = EventBus()

        bus.emit(CoreSEOEventType.PAGE_DISCOVERED, "test-evt-2", data={"url": "https://a.com"})
        bus.emit(CoreSEOEventType.PAGE_DISCOVERED, "test-evt-2", data={"url": "https://b.com"})
        bus.emit(CoreSEOEventType.PAGE_DISCOVERED, "test-evt-2", data={"url": "https://c.com"})

        counters = EventBus.get_counters("test-evt-2")
        assert counters["pages_discovered"] == 3
        EventBus.clear_audit_state("test-evt-2")

    def test_page_completed_increments_pages_crawled(self):
        EventBus.reset_counters("test-evt-3")
        bus = EventBus()

        bus.emit(CoreSEOEventType.PAGE_COMPLETED, "test-evt-3", data={"url": "https://a.com", "passed": 15})
        counters = EventBus.get_counters("test-evt-3")
        assert counters["pages_crawled"] == 1
        EventBus.clear_audit_state("test-evt-3")

    def test_page_failed_increments_only_pages_failed(self):
        """PAGE_FAILED must increment pages_failed ONLY, not pages_crawled (bug fix)."""
        EventBus.reset_counters("test-evt-4")
        bus = EventBus()

        bus.emit(CoreSEOEventType.PAGE_FAILED, "test-evt-4", data={"url": "https://a.com", "error": "timeout", "stage": "fetch"})
        counters = EventBus.get_counters("test-evt-4")
        assert counters["pages_failed"] == 1
        assert counters["pages_crawled"] == 0  # must NOT increment
        EventBus.clear_audit_state("test-evt-4")

    def test_rule_checked_passed_increments_rules_passed(self):
        EventBus.reset_counters("test-evt-5")
        bus = EventBus()

        bus.emit(CoreSEOEventType.RULE_CHECKED, "test-evt-5", data={"url": "u", "rule_id": "r1", "passed": True})
        counters = EventBus.get_counters("test-evt-5")
        assert counters["rules_passed"] == 1
        assert counters["rules_failed"] == 0
        assert counters["rules_total"] == 1
        EventBus.clear_audit_state("test-evt-5")

    def test_rule_checked_failed_increments_rules_failed(self):
        EventBus.reset_counters("test-evt-6")
        bus = EventBus()

        bus.emit(CoreSEOEventType.RULE_CHECKED, "test-evt-6", data={"url": "u", "rule_id": "r1", "passed": False})
        counters = EventBus.get_counters("test-evt-6")
        assert counters["rules_passed"] == 0
        assert counters["rules_failed"] == 1
        assert counters["rules_total"] == 1
        EventBus.clear_audit_state("test-evt-6")

    def test_mixed_rule_checked_counts(self):
        EventBus.reset_counters("test-evt-7")
        bus = EventBus()

        bus.emit(CoreSEOEventType.RULE_CHECKED, "test-evt-7", data={"rule_id": "r1", "passed": True})
        bus.emit(CoreSEOEventType.RULE_CHECKED, "test-evt-7", data={"rule_id": "r2", "passed": False})
        bus.emit(CoreSEOEventType.RULE_CHECKED, "test-evt-7", data={"rule_id": "r3", "passed": True})
        counters = EventBus.get_counters("test-evt-7")
        assert counters["rules_passed"] == 2
        assert counters["rules_failed"] == 1
        assert counters["rules_total"] == 3
        EventBus.clear_audit_state("test-evt-7")


class TestEventBusStream:
    """Verify events are stored in and retrieved from Redis stream."""

    def test_events_persisted_to_stream(self):
        bus = EventBus()
        bus.emit(CoreSEOEventType.PAGE_DISCOVERED, "test-stream-1", data={"url": "https://a.com"})
        bus.emit(CoreSEOEventType.PAGE_STARTED, "test-stream-1", data={"url": "https://a.com"})

        events = EventBus.get_events_for_audit("test-stream-1")
        assert len(events) == 2
        assert events[0].event_type == "page_discovered"
        assert events[1].event_type == "page_started"
        EventBus.clear_audit_state("test-stream-1")

    def test_event_ordering_preserved(self):
        bus = EventBus()
        for i in range(5):
            bus.emit(CoreSEOEventType.PAGE_DISCOVERED, "test-order-1", data={"url": f"https://a{i}.com"})

        events = EventBus.get_events_for_audit("test-order-1")
        assert len(events) == 5
        urls = [e.data.get("url") for e in events]
        assert urls == [f"https://a{i}.com" for i in range(5)]
        EventBus.clear_audit_state("test-order-1")

    def test_get_events_empty_for_unknown(self):
        events = EventBus.get_events_for_audit("nonexistent-stream")
        assert events == []


class TestEventBusTTL:
    """Verify all Redis keys have the correct TTL."""

    def test_all_keys_have_ttl(self):
        EventBus.set_audit_state("test-ttl-1", status="running", total_pages=5)
        EventBus.reset_counters("test-ttl-1")
        bus = EventBus()
        bus.emit(CoreSEOEventType.PAGE_DISCOVERED, "test-ttl-1", data={"url": "https://a.com"})

        client = _get_sync_redis()
        assert client is not None

        assert client.ttl(_redis_key("test-ttl-1", "counters")) == REDIS_TTL_SECONDS
        assert client.ttl(_redis_key("test-ttl-1", "state")) == REDIS_TTL_SECONDS
        assert client.ttl(f"core_seo:events:test-ttl-1") == REDIS_TTL_SECONDS
        EventBus.clear_audit_state("test-ttl-1")

    def test_ttl_is_3600(self):
        assert REDIS_TTL_SECONDS == 3600


class TestEventBusAuditState:
    """Verify audit state read/write via Redis hash."""

    def test_set_and_get_state(self):
        EventBus.set_audit_state("test-state-1", status="running", total_pages=10)
        state = EventBus.get_audit_state("test-state-1")
        assert state.get("status") == "running"
        assert state.get("total_pages") == 10
        EventBus.clear_audit_state("test-state-1")

    def test_clear_removes_all_keys(self):
        EventBus.set_audit_state("test-clear-1", status="completed")
        EventBus.reset_counters("test-clear-1")
        EventBus.clear_audit_state("test-clear-1")

        state = EventBus.get_audit_state("test-clear-1")
        counters = EventBus.get_counters("test-clear-1")
        assert state == {}
        assert counters == EventBus.get_counters("nonexistent")  # returns defaults

    def test_get_status_combines_counters_and_state(self):
        EventBus.reset_counters("test-status-1")
        EventBus.set_audit_state("test-status-1", status="running", start_url="https://example.com")
        bus = EventBus()
        bus.emit(CoreSEOEventType.PAGE_DISCOVERED, "test-status-1", data={"url": "https://a.com"})

        status = EventBus.get_status("test-status-1")
        assert status["status"] == "running"
        assert status["start_url"] == "https://example.com"
        assert status["pages_discovered"] == 1
        EventBus.clear_audit_state("test-status-1")


class TestEventBusSubscribers:
    """Verify in-process subscriber dispatch still works."""

    def test_subscriber_receives_events(self):
        EventBus._subscribers.clear()
        received = []

        def callback(event):
            received.append(event)

        bus = EventBus()
        bus.subscribe("test-sub-1", callback)
        bus.emit(CoreSEOEventType.PAGE_DISCOVERED, "test-sub-1", data={"url": "https://a.com"})

        assert len(received) == 1
        assert received[0].event_type == "page_discovered"
        EventBus._subscribers.clear()
        EventBus.clear_audit_state("test-sub-1")

    def test_subscriber_all_receives_any_audit(self):
        EventBus._subscribers.clear()
        received = []

        def callback(event):
            received.append(event)

        bus = EventBus()
        bus.subscribe_all(callback)
        bus.emit(CoreSEOEventType.PAGE_DISCOVERED, "test-sub-all", data={"url": "https://a.com"})

        assert len(received) == 1
        EventBus._subscribers.clear()
        EventBus.clear_audit_state("test-sub-all")
