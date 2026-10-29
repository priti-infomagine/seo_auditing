"""Tests for the Content pipeline (ContentCrawlerService)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.modules.category_check.content.events import ContentEventBus
from app.modules.category_check.content.models import (
    ContentEventType,
    CrawlResult,
    DiscoveredURL,
    PageScore,
)
from app.modules.category_check.content.pipeline import ContentCrawlerService


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
        return [DiscoveredURL(**u) for u in self._urls]


class TestContentCrawlerService:
    @pytest.fixture
    def mock_service(self, sample_html):
        service = ContentCrawlerService()
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
        events = ContentEventBus.get_events_for_audit(audit_id)
        assert len(events) > 0
        event_types = [e.event_type for e in events]
        assert ContentEventType.AUDIT_STARTED.value in event_types
        assert ContentEventType.PAGE_COMPLETED.value in event_types

    @pytest.mark.asyncio
    async def test_process_page_returns_score(self, mock_service, sample_html):
        from app.modules.category_check.core_seo.models import CrawlResult as CoreCrawlResult

        crawl_result = CoreCrawlResult(
            url="https://example.com",
            html=sample_html,
            status_code=200,
            success=True,
        )
        page_score = await mock_service.process_page(
            "https://example.com",
            audit_id="test-content-audit",
            index=0,
            total=1,
            crawl_result=crawl_result,
        )
        assert isinstance(page_score, PageScore)
        assert page_score.total == 13

    @pytest.mark.asyncio
    async def test_get_audit_status_unknown(self, mock_service):
        result = mock_service.get_audit_status("nonexistent-content")
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
        assert "pass_percentage" in status
        EventBus_cleanup(audit_id)


def EventBus_cleanup(audit_id):
    ContentEventBus.clear_audit_state(audit_id)


class TestContentServiceIsolation:
    """Verify content and core_seo events are isolated via separate Redis keys."""

    @pytest.mark.asyncio
    async def test_separate_redis_namespaces(self, sample_html):
        from app.modules.category_check.core_seo.events import EventBus

        service = ContentCrawlerService()
        service.crawler = MockCrawler(sample_html)
        service.page_discoverer = MockPageDiscoverer()

        audit_id = await service.start_audit(
            "https://example.com",
            max_pages=1,
            max_depth=1,
            audit_id="test-namespace-isolation",
        )

        core_events = EventBus.get_events_for_audit("test-namespace-isolation")
        content_events = ContentEventBus.get_events_for_audit("test-namespace-isolation")

        # Core events should be empty (content service runs independently)
        assert len(core_events) == 0

        # Content events should have data
        assert len(content_events) > 0
        assert any(e.event_type == "audit_completed" for e in content_events)

        EventBus.clear_audit_state("test-namespace-isolation")
        ContentEventBus.clear_audit_state("test-namespace-isolation")
