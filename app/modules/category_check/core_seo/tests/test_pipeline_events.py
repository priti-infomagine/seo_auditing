"""Tests for pipeline event emission ordering and per-rule events."""
from __future__ import annotations

import pytest

from app.modules.category_check.core_seo.events import EventBus, _get_sync_redis
from app.modules.category_check.core_seo.models import (
    CoreSEOEventType,
    CrawlResult,
)
from app.modules.category_check.core_seo.pipeline import CoreSEOCrawlerService


def _redis_available():
    return _get_sync_redis() is not None


pytestmark = pytest.mark.skipif(
    not _redis_available(),
    reason="Redis not available on 127.0.0.1:6379",
)


class MockCrawler:
    def __init__(self, html: str = "", status_code: int = 200):
        self._html = html
        self._status_code = status_code

    async def crawl(self, url: str) -> CrawlResult:
        return CrawlResult(
            url=url,
            html=self._html,
            status_code=self._status_code,
            success=True,
            response_time_ms=100,
            final_url=url,
        )


class MockPageDiscoverer:
    def __init__(self, urls=None):
        self._urls = urls or [{"url": "https://example.com", "normalized_url": "https://example.com/", "source_type": "seed", "depth": 0}]

    async def discover_pages(self, start_url: str, max_pages: int = 10, max_depth: int = 3):
        from app.modules.category_check.core_seo.models import DiscoveredURL
        return [DiscoveredURL(**u) for u in self._urls]


class TestPipelineEventOrdering:
    """Verify the exact event sequence for a single page audit."""

    @pytest.fixture
    def service(self, sample_html):
        svc = CoreSEOCrawlerService()
        svc.crawler = MockCrawler(sample_html)
        svc.page_discoverer = MockPageDiscoverer()
        return svc

    @pytest.mark.asyncio
    async def test_single_page_event_sequence(self, service):
        """Single page emits: page_queued → page_started → fetch_started →
        parsed → 18× rule_checked → page_completed."""
        audit_id = await service.start_audit(
            "https://example.com",
            max_pages=1, max_depth=1,
        )

        events = EventBus.get_events_for_audit(audit_id)
        page_events = [
            e for e in events
            if e.url == "https://example.com" and e.event_type in (
                CoreSEOEventType.PAGE_QUEUED.value,
                CoreSEOEventType.PAGE_STARTED.value,
                CoreSEOEventType.FETCH_STARTED.value,
                CoreSEOEventType.PARSED.value,
                CoreSEOEventType.RULE_CHECKED.value,
                CoreSEOEventType.PAGE_COMPLETED.value,
            )
        ]

        event_types = [e.event_type for e in page_events]

        # First event must be page_queued
        assert event_types[0] == "page_queued"
        # Then page_started, fetch_started, parsed
        assert "page_started" in event_types[:4]
        assert "fetch_started" in event_types[:4]
        assert "parsed" in event_types[:4]
        # parsed comes after fetch_started
        assert event_types.index("parsed") > event_types.index("fetch_started")
        # Last event must be page_completed
        assert event_types[-1] == "page_completed"
        EventBus.clear_audit_state(audit_id)

    @pytest.mark.asyncio
    async def test_exactly_18_rule_checked_events(self, service):
        """Exactly 18 rule_checked events emitted per page."""
        audit_id = await service.start_audit(
            "https://example.com",
            max_pages=1, max_depth=1,
        )

        events = EventBus.get_events_for_audit(audit_id)
        rule_events = [e for e in events if e.event_type == "rule_checked"]
        assert len(rule_events) == 18
        EventBus.clear_audit_state(audit_id)

    @pytest.mark.asyncio
    async def test_rule_checked_payload_has_checked_and_of(self, service):
        """Each rule_checked event has checked and of fields."""
        audit_id = await service.start_audit(
            "https://example.com",
            max_pages=1, max_depth=1,
        )

        events = EventBus.get_events_for_audit(audit_id)
        rule_events = [e for e in events if e.event_type == "rule_checked"]
        assert len(rule_events) == 18

        for i, evt in enumerate(rule_events, 1):
            assert evt.data.get("checked") == i
            assert evt.data.get("of") == 18
            assert "rule_id" in evt.data
            assert "passed" in evt.data

        # Verify rule IDs are sequential slugs
        rule_ids = [e.data["rule_id"] for e in rule_events]
        assert len(set(rule_ids)) == 18  # all unique
        EventBus.clear_audit_state(audit_id)

    @pytest.mark.asyncio
    async def test_counters_match_events(self, service):
        """Counter values should match the emitted events."""
        audit_id = await service.start_audit(
            "https://example.com",
            max_pages=1, max_depth=1,
        )

        events = EventBus.get_events_for_audit(audit_id)
        counters = EventBus.get_counters(audit_id)

        rule_events = [e for e in events if e.event_type == "rule_checked"]
        page_completed = [e for e in events if e.event_type == "page_completed"]
        page_discovered = [e for e in events if e.event_type == "page_discovered"]

        rules_passed = sum(1 for e in rule_events if e.data.get("passed"))
        rules_failed = sum(1 for e in rule_events if not e.data.get("passed"))

        assert counters["rules_passed"] == rules_passed
        assert counters["rules_failed"] == rules_failed
        assert counters["pages_crawled"] == len(page_completed)
        assert counters["pages_discovered"] == len(page_discovered)
        EventBus.clear_audit_state(audit_id)


class TestPageFailureEvents:
    """Verify page_failed event is emitted on fetch errors."""

    @pytest.mark.asyncio
    async def test_failed_page_emits_page_failed(self):
        """A failed fetch emits PAGE_FAILED, not PAGE_COMPLETED."""
        from unittest.mock import AsyncMock

        service = CoreSEOCrawlerService()
        service.crawler.crawl = AsyncMock(side_effect=Exception("Network error"))
        service.page_discoverer = MockPageDiscoverer()

        audit_id = await service.start_audit(
            "https://example.com",
            max_pages=1, max_depth=1,
        )

        events = EventBus.get_events_for_audit(audit_id)
        event_types = [e.event_type for e in events]
        assert "page_failed" in event_types
        assert "page_completed" not in event_types

        counters = EventBus.get_counters(audit_id)
        assert counters["pages_failed"] == 1
        assert counters["pages_crawled"] == 0

        EventBus.clear_audit_state(audit_id)

    @pytest.mark.asyncio
    async def test_failed_page_has_stage_field(self):
        """PAGE_FAILED event payload includes a stage field."""
        from unittest.mock import AsyncMock

        service = CoreSEOCrawlerService()
        service.crawler.crawl = AsyncMock(side_effect=ConnectionError("DNS failure"))
        service.page_discoverer = MockPageDiscoverer()

        audit_id = await service.start_audit(
            "https://example.com",
            max_pages=1, max_depth=1,
        )

        events = EventBus.get_events_for_audit(audit_id)
        failed_events = [e for e in events if e.event_type == "page_failed"]
        assert len(failed_events) == 1
        assert failed_events[0].data.get("stage") == "fetch"
        assert "error" in failed_events[0].data

        EventBus.clear_audit_state(audit_id)


class TestAuditCompletionEvents:
    """Verify audit_completed event is emitted at the end."""

    @pytest.mark.asyncio
    async def test_audit_completed_emitted(self, sample_html):
        service = CoreSEOCrawlerService()
        service.crawler = MockCrawler(sample_html)
        service.page_discoverer = MockPageDiscoverer()

        audit_id = await service.start_audit(
            "https://example.com",
            max_pages=1, max_depth=1,
        )

        events = EventBus.get_events_for_audit(audit_id)
        event_types = [e.event_type for e in events]
        assert "audit_completed" in event_types

        # audit_completed should be the last event
        assert event_types[-1] == "audit_completed"
        EventBus.clear_audit_state(audit_id)

    @pytest.mark.asyncio
    async def test_audit_state_set_to_completed(self, sample_html):
        service = CoreSEOCrawlerService()
        service.crawler = MockCrawler(sample_html)
        service.page_discoverer = MockPageDiscoverer()

        audit_id = await service.start_audit(
            "https://example.com",
            max_pages=1, max_depth=1,
        )

        state = EventBus.get_audit_state(audit_id)
        assert state.get("status") == "completed"
        EventBus.clear_audit_state(audit_id)
