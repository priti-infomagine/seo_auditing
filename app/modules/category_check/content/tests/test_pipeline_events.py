"""Tests for content pipeline event emission ordering and per-rule events."""
from __future__ import annotations

import pytest

from app.modules.category_check.content.events import ContentEventBus, _get_sync_redis
from app.modules.category_check.content.models import (
    ContentEventType,
    CrawlResult,
)
from app.modules.category_check.content.pipeline import ContentCrawlerService


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

    async def discover_pages(self, start_url: str, max_pages: int = 10, max_depth: int = 3, **kwargs):
        from app.modules.category_check.content.models import DiscoveredURL
        return [DiscoveredURL(**u) for u in self._urls]


class TestContentPipelineEventOrdering:
    @pytest.fixture
    def service(self, sample_html):
        svc = ContentCrawlerService()
        svc.crawler = MockCrawler(sample_html)
        svc.page_discoverer = MockPageDiscoverer()
        return svc

    @pytest.mark.asyncio
    async def test_single_page_event_sequence(self, service):
        """Single page emits audit_started → page_discovered → page_started →
        parsed → 13× rule_checked → page_completed → audit_completed."""
        audit_id = await service.start_audit(
            "https://example.com",
            max_pages=1, max_depth=1,
        )

        events = ContentEventBus.get_events_for_audit(audit_id)
        event_types = [e.event_type for e in events]

        assert event_types[0] == "audit_started"
        assert "page_started" in event_types
        assert "parsed" in event_types
        assert "page_completed" in event_types
        assert event_types[-1] == "audit_completed"

        ContentEventBus.clear_audit_state(audit_id)

    @pytest.mark.asyncio
    async def test_exactly_13_rule_checked_events(self, service):
        audit_id = await service.start_audit(
            "https://example.com",
            max_pages=1, max_depth=1,
        )

        events = ContentEventBus.get_events_for_audit(audit_id)
        rule_events = [e for e in events if e.event_type == "rule_checked"]
        assert len(rule_events) == 13

        ContentEventBus.clear_audit_state(audit_id)

    @pytest.mark.asyncio
    async def test_rule_checked_payload_has_checked_and_of(self, service):
        audit_id = await service.start_audit(
            "https://example.com",
            max_pages=1, max_depth=1,
        )

        events = ContentEventBus.get_events_for_audit(audit_id)
        rule_events = [e for e in events if e.event_type == "rule_checked"]
        assert len(rule_events) == 13

        for i, evt in enumerate(rule_events, 1):
            assert evt.data.get("checked") == i
            assert evt.data.get("of") == 13
            assert "rule_id" in evt.data
            assert "passed" in evt.data

        rule_ids = [e.data["rule_id"] for e in rule_events]
        assert len(set(rule_ids)) == 13

        ContentEventBus.clear_audit_state(audit_id)

    @pytest.mark.asyncio
    async def test_counters_match_events(self, service):
        audit_id = await service.start_audit(
            "https://example.com",
            max_pages=1, max_depth=1,
        )

        events = ContentEventBus.get_events_for_audit(audit_id)
        counters = ContentEventBus.get_counters(audit_id)

        rule_events = [e for e in events if e.event_type == "rule_checked"]
        rules_passed = sum(1 for e in rule_events if e.data.get("passed"))
        rules_failed = sum(1 for e in rule_events if not e.data.get("passed"))

        assert counters["rules_passed"] == rules_passed
        assert counters["rules_failed"] == rules_failed

        ContentEventBus.clear_audit_state(audit_id)


class TestContentPageFailureEvents:
    @pytest.mark.asyncio
    async def test_failed_page_emits_page_failed(self):
        from unittest.mock import AsyncMock

        service = ContentCrawlerService()
        service.crawler.crawl = AsyncMock(side_effect=Exception("Network error"))
        service.page_discoverer = MockPageDiscoverer()

        audit_id = await service.start_audit(
            "https://example.com",
            max_pages=1, max_depth=1,
        )

        events = ContentEventBus.get_events_for_audit(audit_id)
        event_types = [e.event_type for e in events]
        assert "page_failed" in event_types

        counters = ContentEventBus.get_counters(audit_id)
        assert counters["pages_failed"] == 1

        ContentEventBus.clear_audit_state(audit_id)
