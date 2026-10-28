"""Tests for the Pipeline (CoreSEOCrawlerService)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.modules.category_check.core_seo.models import (
    CoreSEOEventType,
    CrawlResult,
    DiscoveredURL,
    PageScore,
)
from app.modules.category_check.core_seo.events import EventBus
from app.modules.category_check.core_seo.pipeline import CoreSEOCrawlerService
from app.modules.separate_checks.sitemap_check.errors import (
    NO_SITEMAP_MESSAGE,
    NoSitemapAvailableError,
)


class MockCrawler:
    """Mock crawler that returns pre-defined HTML."""
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
    """Mock discoverer that returns a single URL."""
    def __init__(self, urls=None):
        self._urls = urls or [{"url": "https://example.com", "normalized_url": "https://example.com/", "source_type": "seed", "depth": 0}]

    async def discover_pages(self, start_url: str, max_pages: int = 10, max_depth: int = 3, **kwargs):
        from app.modules.category_check.core_seo.models import DiscoveredURL
        return [DiscoveredURL(**u) for u in self._urls]


class TestCoreSEOCrawlerService:
    @pytest.fixture
    def mock_service(self, sample_html):
        """Create a service with mocked crawler and discoverer."""
        service = CoreSEOCrawlerService()
        service.crawler = MockCrawler(sample_html)
        service.page_discoverer = MockPageDiscoverer()
        return service

    @pytest.mark.asyncio
    async def test_start_audit_returns_audit_id(self, mock_service):
        audit_id = await mock_service.start_audit(
            "https://example.com",
            max_pages=1,
            max_depth=1,
        )
        assert isinstance(audit_id, str)
        assert len(audit_id) > 0

    @pytest.mark.asyncio
    async def test_start_audit_publishes_events(self, mock_service):
        audit_id = await mock_service.start_audit(
            "https://example.com",
            max_pages=1,
            max_depth=1,
        )
        events = EventBus.get_events_for_audit(audit_id)
        assert len(events) > 0
        event_types = [e.event_type for e in events]
        assert CoreSEOEventType.PAGE_DISCOVERED.value in event_types
        assert CoreSEOEventType.AUDIT_STARTED.value in event_types

    @pytest.mark.asyncio
    async def test_process_page_returns_score_and_result(self, mock_service, sample_html):
        page_score, crawl_result = await mock_service.process_page(
            "https://example.com",
            audit_id="test-audit",
            index=0,
            total=1,
        )
        assert isinstance(page_score, PageScore)
        assert page_score.url == "https://example.com"
        assert isinstance(crawl_result, CrawlResult)
        assert crawl_result.status_code == 200

    @pytest.mark.asyncio
    async def test_get_audit_status_unknown(self, mock_service):
        result = mock_service.get_audit_status("nonexistent")
        assert result["status"] == "unknown"

    @pytest.mark.asyncio
    async def test_get_audit_status_found(self, mock_service):
        audit_id = await mock_service.start_audit(
            "https://example.com",
            max_pages=1,
            max_depth=1,
        )
        status = mock_service.get_audit_status(audit_id)
        assert status["status"] == "completed"
        assert status["total_pages"] == 1
        assert "pages_done" in status
        assert "pass_percentage" in status

    @pytest.mark.asyncio
    async def test_crawl_failure_emits_event(self, mock_service):
        mock_service.crawler = MockCrawler()
        mock_service.crawler.crawl = AsyncMock(side_effect=Exception("Network error"))
        mock_service.page_discoverer = MockPageDiscoverer()

        page_score, crawl_result = await mock_service.process_page(
            "https://example.com",
            audit_id="error-audit",
            index=0,
            total=1,
        )
        assert page_score.passed == 0
        assert crawl_result.success is False

        events = EventBus.get_events_for_audit("error-audit")
        event_types = [e.event_type for e in events]
        assert CoreSEOEventType.PAGE_FAILED.value in event_types

    @pytest.mark.asyncio
    async def test_start_audit_no_sitemap_falls_back_to_bfs(self, sample_html):
        """When the discoverer finds no sitemap and returns an empty list,
        the audit should NOT abort — it should complete normally (with zero
        pages in this mock scenario) instead of emitting an AUDIT_FAILED event."""

        class _EmptyDiscoverer:
            async def discover_pages(self, start_url, max_pages=10, max_depth=3, **kwargs):
                return []

        service = CoreSEOCrawlerService()
        service.crawler = MockCrawler(sample_html)
        service.page_discoverer = _EmptyDiscoverer()

        audit_id = await service.start_audit(
            "https://example.com", max_pages=1, max_depth=1,
        )

        assert isinstance(audit_id, str)
        events = EventBus.get_events_for_audit(audit_id)
        event_types = {e.event_type for e in events}

        # Should NOT have an AUDIT_FAILED event
        assert CoreSEOEventType.AUDIT_FAILED.value not in event_types
        # Should have AUDIT_COMPLETED
        assert CoreSEOEventType.AUDIT_COMPLETED.value in event_types
        assert CoreSEOEventType.AUDIT_STARTED.value in event_types

        state = EventBus.get_audit_state(audit_id)
        assert state.get("status") == "completed"

        EventBus.clear_audit_state(audit_id)

    @pytest.mark.asyncio
    async def test_start_audit_no_sitemap_required_raises(self, sample_html):
        """When require_sitemap=True and discoverer returns no sitemap-sourced URLs,
        start_audit emits AUDIT_FAILED, sets state to failed, and raises."""

        class _NoSitemapDiscoverer:
            async def discover_pages(self, start_url, max_pages=10, max_depth=3, **kwargs):
                return [DiscoveredURL(
                    url=start_url,
                    normalized_url=start_url,
                    source_type="seed",
                    depth=0,
                )]

        service = CoreSEOCrawlerService()
        service.crawler = MockCrawler(sample_html)
        service.page_discoverer = _NoSitemapDiscoverer()
        audit_id = "test-no-sitemap-gate"

        with pytest.raises(NoSitemapAvailableError) as exc_info:
            await service.start_audit(
                start_url="https://example.com",
                max_pages=1, max_depth=1,
                audit_id=audit_id,
                require_sitemap=True,
            )
        assert exc_info.value.message == NO_SITEMAP_MESSAGE

        events = EventBus.get_events_for_audit(audit_id)
        event_types = {e.event_type for e in events}
        assert CoreSEOEventType.AUDIT_FAILED.value in event_types

        state = EventBus.get_audit_state(audit_id)
        assert state.get("status") == "failed"
        assert state.get("error") == NO_SITEMAP_MESSAGE

        EventBus.clear_audit_state(audit_id)

    @pytest.mark.asyncio
    async def test_start_audit_sitemap_required_proceeds_when_sitemap_present(self, sample_html):
        """When require_sitemap=True and discoverer returns sitemap-sourced URLs,
        start_audit proceeds normally (no raise, audit completes)."""

        class _HasSitemapDiscoverer:
            async def discover_pages(self, start_url, max_pages=10, max_depth=3, **kwargs):
                return [DiscoveredURL(
                    url=start_url,
                    normalized_url=start_url,
                    source_type="sitemap",
                    depth=0,
                )]

        service = CoreSEOCrawlerService()
        service.crawler = MockCrawler(sample_html)
        service.page_discoverer = _HasSitemapDiscoverer()

        audit_id = await service.start_audit(
            start_url="https://example.com",
            max_pages=1, max_depth=1,
            require_sitemap=True,
        )

        events = EventBus.get_events_for_audit(audit_id)
        event_types = {e.event_type for e in events}
        assert CoreSEOEventType.AUDIT_FAILED.value not in event_types
        assert CoreSEOEventType.AUDIT_COMPLETED.value in event_types

        state = EventBus.get_audit_state(audit_id)
        assert state.get("status") == "completed"

        EventBus.clear_audit_state(audit_id)

    @pytest.mark.asyncio
    async def test_get_report_returns_none_for_unknown(self, mock_service):
        result = mock_service.get_report("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_report_returns_result_after_audit(self, mock_service, sample_html):
        audit_id = await mock_service.start_audit(
            "https://example.com",
            max_pages=1,
            max_depth=1,
        )
        report = mock_service.get_report(audit_id)
        assert report is not None
        assert report.status == "completed"
        assert report.summary["pages_total"] == 1
        assert "pass_percentage" in report.summary


class TestEventBus:
    def test_event_bus_publishes_and_retrieves(self):
        from app.modules.category_check.core_seo.events import EventBus, PipelineEvent

        EventBus._subscribers.clear()

        bus = EventBus()
        asyncio.run(bus.publish(PipelineEvent(
            event_type=CoreSEOEventType.PAGE_DISCOVERED.value,
            audit_id="test-123",
            payload={"url": "https://example.com"},
        )))

        events = EventBus.get_events_for_audit("test-123")
        assert len(events) >= 1
        assert events[0].audit_id == "test-123"

        EventBus.clear_audit_state("test-123")

    def test_event_bus_counters(self):
        from app.modules.category_check.core_seo.events import EventBus

        EventBus.reset_counters("test-counter-123")
        counters = EventBus.get_counters("test-counter-123")
        assert counters["pages_discovered"] == 0

        EventBus.clear_audit_state("test-counter-123")

    def test_event_bus_subscribe(self):
        from app.modules.category_check.core_seo.events import EventBus

        EventBus._subscribers.clear()
        bus = EventBus()
        received = []

        def callback(event):
            received.append(event)

        bus.subscribe("test-sub-123", callback)
        bus.emit(CoreSEOEventType.PAGE_DISCOVERED, "test-sub-123",
                 data={"url": "https://example.com"})

        assert len(received) == 1

        EventBus.clear_audit_state("test-sub-123")
