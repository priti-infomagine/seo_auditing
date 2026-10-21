"""Tests for the Celery task architecture (run_audit dispatching crawl_page_task)."""
from __future__ import annotations

import pytest

from app.modules.category_check.core_seo.pipeline import CoreSEOCrawlerService
from app.modules.category_check.core_seo.models import (
    CrawlResult,
)
from app.modules.category_check.core_seo.tasks import (
    crawl_page_inline,
    run_audit_inline,
    CELERY_AVAILABLE,
)
from app.modules.category_check.core_seo.events import EventBus
from app.modules.category_check.core_seo.models import CoreSEOEventType


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
        self._urls = urls or [
            {"url": "https://example.com", "normalized_url": "https://example.com/",
             "source_type": "seed", "depth": 0}
        ]

    async def discover_pages(self, start_url: str, max_pages: int = 10, max_depth: int = 3):
        from app.modules.category_check.core_seo.models import DiscoveredURL
        return [DiscoveredURL(**u) for u in self._urls]


SAMPLE_HTML = """
<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="A sample page for testing with good SEO practices and enough content to pass all rule checks.">
<meta name="robots" content="index, follow">
<title>Comprehensive Sample Page Title For SEO Testing</title>
<link rel="canonical" href="https://example.com/page">
<link rel="icon" href="/favicon.ico">
</head><body>
<h1>Main Heading For The Page</h1>
<h2>Section One</h2>
<p>This is a paragraph with sufficient content to pass all SEO rule checks. We need words.</p>
<p>Another paragraph of content to ensure adequate word count for SEO evaluation.</p>
<p>Additional paragraph to provide more content for testing purposes.</p>
<a href="https://example.com/page2">Internal Link</a>
<a href="https://external.com/page">External Link</a>
<img src="/image.png" alt="Sample image alt text">
</body></html>
"""


class TestCrawlPageTask:
    def test_crawl_page_inline_returns_score(self, sample_html):
        """crawl_page_inline returns serialized page score with rule results."""
        service = CoreSEOCrawlerService()
        service.crawler = MockCrawler(sample_html)

        result = crawl_page_inline(
            "https://example.com",
            audit_id="test-inline-123",
            index=0, total=1,
        )

        assert result["url"] == "https://example.com"
        assert result["status_code"] == 200
        assert result["success"] is True
        assert "pass_percentage" in result
        assert "rule_results" in result
        assert "passed" in result
        assert "failed" in result

    def test_crawl_page_inline_has_rule_results(self, sample_html):
        """The serialized result includes all 18 rules."""
        import app.modules.category_check.core_seo.tasks as tasks_mod
        original_service = tasks_mod.CoreSEOCrawlerService

        class MockService(original_service):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.crawler = MockCrawler(sample_html)

        tasks_mod.CoreSEOCrawlerService = MockService
        try:
            result = crawl_page_inline(
                "https://example.com",
                audit_id="test-rules-123",
                index=0, total=1,
            )
            assert len(result["rule_results"]) == 18
        finally:
            tasks_mod.CoreSEOCrawlerService = original_service

    def test_crawl_page_inline_error_handling(self):
        """When crawl fails, crawl_page returns error result."""
        import app.modules.category_check.core_seo.tasks as tasks_mod
        original_service = tasks_mod.CoreSEOCrawlerService

        class FailingCrawler:
            async def crawl(self, url):
                raise ConnectionError("Network unreachable")

        class FailingService(original_service):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.crawler = FailingCrawler()

        tasks_mod.CoreSEOCrawlerService = FailingService
        try:
            result = crawl_page_inline(
                "https://example.com",
                audit_id="test-fail-123",
            )
            assert result["success"] is False
            assert "error" in result
        finally:
            tasks_mod.CoreSEOCrawlerService = original_service


class TestRunAudit:
    def test_run_audit_inline_creates_audit(self, sample_html):
        """run_audit_inline creates an audit and completes it."""
        service = CoreSEOCrawlerService()
        service.crawler = MockCrawler(sample_html)
        service.page_discoverer = MockPageDiscoverer([
            {"url": "https://example.com", "normalized_url": "https://example.com/",
             "source_type": "seed", "depth": 0}
        ])

        # Patch the service in the inline runner
        import app.modules.category_check.core_seo.tasks as tasks_mod
        original_service = tasks_mod.CoreSEOCrawlerService

        class PatchedService(original_service):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.crawler = MockCrawler(sample_html)
                self.page_discoverer = MockPageDiscoverer([
                    {"url": "https://example.com", "normalized_url": "https://example.com/",
                     "source_type": "seed", "depth": 0}
                ])

        tasks_mod.CoreSEOCrawlerService = PatchedService
        try:
            audit_id = run_audit_inline("https://example.com", max_pages=1, max_depth=1)
            assert isinstance(audit_id, str)
            assert len(audit_id) > 0
        finally:
            tasks_mod.CoreSEOCrawlerService = original_service

    def test_run_audit_inline_emits_events(self, sample_html):
        """Events are emitted during inline audit run."""
        service = CoreSEOCrawlerService()
        service.crawler = MockCrawler(sample_html)
        service.page_discoverer = MockPageDiscoverer()

        import app.modules.category_check.core_seo.tasks as tasks_mod
        original_service = tasks_mod.CoreSEOCrawlerService

        class PatchedService(original_service):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.crawler = MockCrawler(sample_html)
                self.page_discoverer = MockPageDiscoverer()

        tasks_mod.CoreSEOCrawlerService = PatchedService
        try:
            audit_id = run_audit_inline("https://example.com", max_pages=1, max_depth=1)

            # Events are stored in Redis stream
            events = EventBus.get_events_for_audit(audit_id)
            event_types = {e.event_type for e in events}
            assert CoreSEOEventType.AUDIT_STARTED.value in event_types
            assert CoreSEOEventType.PAGE_DISCOVERED.value in event_types
            assert CoreSEOEventType.RULE_CHECKED.value in event_types
            assert CoreSEOEventType.AUDIT_COMPLETED.value in event_types

            EventBus.clear_audit_state(audit_id)
        finally:
            tasks_mod.CoreSEOCrawlerService = original_service


class TestCeleryTaskStructure:
    def test_crawl_page_task_exists(self):
        """crawl_page_task is available for Celery dispatch."""
        from app.modules.category_check.core_seo.tasks import crawl_page_task
        assert crawl_page_task is not None

    def test_run_audit_task_exists(self):
        """run_audit is available for Celery dispatch."""
        from app.modules.category_check.core_seo.tasks import run_audit
        assert run_audit is not None

    @pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery not available")
    def test_celery_task_names(self):
        """Celery tasks have proper names registered."""
        from app.modules.category_check.core_seo.tasks import crawl_page_task, run_audit
        if hasattr(crawl_page_task, "name"):
            assert "core_seo" in crawl_page_task.name or "crawl" in crawl_page_task.name
        if hasattr(run_audit, "name"):
            assert "core_seo" in run_audit.name or "audit" in run_audit.name
