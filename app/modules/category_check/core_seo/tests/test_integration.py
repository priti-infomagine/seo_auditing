"""Integration tests for the full Core SEO pipeline (mocked, no external dependencies)."""
from __future__ import annotations

import pytest

from app.modules.category_check.core_seo.pipeline import CoreSEOCrawlerService
from app.modules.category_check.core_seo.models import (
    CrawlResult,
    AuditReport,
    CoreSEOEventType,
    NormalizedResult,
)
from app.modules.category_check.core_seo.summary import summarize_page, summarize_audit


SAMPLE_HTML_FULL = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="A comprehensive sample page with good SEO practices for integration testing the full audit pipeline.">
    <meta name="robots" content="index, follow">
    <title>Comprehensive Sample Page Title For SEO Testing</title>
    <link rel="canonical" href="https://example.com/sample-page">
    <link rel="icon" href="/favicon.ico" type="image/x-icon">
</head>
<body>
    <h1>Main Heading for the Page</h1>
    <h2>Section One</h2>
    <p>This is a paragraph with sufficient content to pass content-based SEO rules. We need words.</p>
    <p>Another paragraph of content for the test page. This ensures we have enough text to pass content-based SEO rules.</p>
    <p>Additional paragraph to provide more content. The SEO rules need sufficient content to evaluate properly.</p>
    <p>More text here to ensure adequate word count for SEO evaluation. Content quality matters for search engine optimization.</p>
    <a href="https://example.com/page-two">Internal Link</a>
    <a href="https://external.com/page">External Link</a>
    <img src="/image.png" alt="Sample image alt text">
    <img src="/image2.png">
</body>
</html>
"""


SAMPLE_HTML_POOR = """
<!DOCTYPE html>
<html>
<head>
    <title>Bad</title>
</head>
<body>
    <h1>One</h1>
    <h1>Two</h1>
    <h2>Test</h2>
</body>
</html>
"""


class TestFullAudit:
    @pytest.fixture
    def service_with_html(self):
        service = CoreSEOCrawlerService()

        class MockCrawler:
            def __init__(self, html):
                self._html = html

            async def crawl(self, url):
                return CrawlResult(
                    url=url, html=self._html, status_code=200,
                    success=True, response_time_ms=100, final_url=url,
                )

        class MockDiscoverer:
            def __init__(self, html):
                self._html = html

            async def discover_pages(self, start_url, max_pages=10, max_depth=3):
                from app.modules.category_check.core_seo.models import DiscoveredURL
                return [DiscoveredURL(
                    url=start_url,
                    normalized_url=start_url,
                    source_type="seed",
                    depth=0,
                )]

        service.crawler = MockCrawler(SAMPLE_HTML_FULL)
        service.page_discoverer = MockDiscoverer(SAMPLE_HTML_FULL)
        return service

    @pytest.fixture
    def service_poor_html(self):
        service = CoreSEOCrawlerService()

        class MockCrawler:
            def __init__(self, html):
                self._html = html

            async def crawl(self, url):
                return CrawlResult(
                    url=url, html=self._html, status_code=200,
                    success=True, response_time_ms=100, final_url=url,
                )

        class MockDiscoverer:
            def __init__(self, html):
                self._html = html

            async def discover_pages(self, start_url, max_pages=10, max_depth=3):
                from app.modules.category_check.core_seo.models import DiscoveredURL
                return [DiscoveredURL(
                    url=start_url, normalized_url=start_url,
                    source_type="seed", depth=0,
                )]

        service.crawler = MockCrawler(SAMPLE_HTML_POOR)
        service.page_discoverer = MockDiscoverer(SAMPLE_HTML_POOR)
        return service

    @pytest.mark.asyncio
    async def test_full_audit_good_seo(self, service_with_html):
        audit_id = await service_with_html.start_audit(
            "https://example.com/sample-page",
            max_pages=1, max_depth=1,
        )

        status = service_with_html.get_audit_status(audit_id)
        assert status["status"] == "completed"
        assert status["pages_done"] >= 1

        report = service_with_html.get_report(audit_id)
        assert report is not None
        assert report.status == "completed"
        assert report.summary["pages_total"] >= 1
        assert "pass_percentage" in report.summary

    @pytest.mark.asyncio
    async def test_audit_events_emitted(self, service_with_html):
        audit_id = await service_with_html.start_audit(
            "https://example.com/sample-page",
            max_pages=1, max_depth=1,
        )

        from app.modules.category_check.core_seo.events import EventBus
        events = EventBus.get_events_for_audit(audit_id)
        event_types = {e.event_type for e in events}

        assert CoreSEOEventType.PAGE_DISCOVERED.value in event_types
        assert CoreSEOEventType.PAGE_STARTED.value in event_types
        assert CoreSEOEventType.FETCH_STARTED.value in event_types
        assert CoreSEOEventType.PARSED.value in event_types
        assert CoreSEOEventType.RULE_CHECKED.value in event_types
        assert CoreSEOEventType.PAGE_COMPLETED.value in event_types
        assert CoreSEOEventType.AUDIT_COMPLETED.value in event_types

    @pytest.mark.asyncio
    async def test_audit_poor_seo_has_failures(self, service_poor_html):
        audit_id = await service_poor_html.start_audit(
            "https://example.com",
            max_pages=1, max_depth=1,
        )

        report = service_poor_html.get_report(audit_id)
        assert report is not None

        all_results = []
        for page in report.pages:
            all_results.extend(page.get("results", []))

        failed_count = sum(1 for r in all_results if not r["passed"])
        assert failed_count > 0

    @pytest.mark.asyncio
    async def test_score_calculation(self, service_with_html):
        audit_id = await service_with_html.start_audit(
            "https://example.com/sample-page",
            max_pages=1, max_depth=1,
        )

        report = service_with_html.get_report(audit_id)
        assert report.summary["pass_percentage"] >= 0
        assert report.summary["pass_percentage"] <= 100

    @pytest.mark.asyncio
    async def test_multiple_pages(self):
        """Test that the pipeline handles multiple discovered pages."""
        service = CoreSEOCrawlerService()

        class MockMultiCrawler:
            async def crawl(self, url):
                return CrawlResult(
                    url=url, html=SAMPLE_HTML_FULL, status_code=200,
                    success=True, response_time_ms=100, final_url=url,
                )

        class MockMultiDiscoverer:
            async def discover_pages(self, start_url, max_pages=10, max_depth=3):
                from app.modules.category_check.core_seo.models import DiscoveredURL
                return [
                    DiscoveredURL(url="https://example.com", normalized_url="https://example.com/",
                                  source_type="seed", depth=0),
                    DiscoveredURL(url="https://example.com/page2", normalized_url="https://example.com/page2",
                                  source_type="sitemap", depth=0),
                    DiscoveredURL(url="https://example.com/page3", normalized_url="https://example.com/page3",
                                  source_type="html_link", depth=1),
                ]

        service.crawler = MockMultiCrawler()
        service.page_discoverer = MockMultiDiscoverer()

        audit_id = await service.start_audit("https://example.com", max_pages=5, max_depth=2)
        status = service.get_audit_status(audit_id)
        assert status["status"] == "completed"
        assert status["pages_done"] == 3


class TestSummaryIntegration:
    def test_summary_with_real_rules(self):
        """Test summary with all 18 real rules."""
        from app.modules.category_check.core_seo.rules.registry import default_registry
        from app.modules.category_check.core_seo.page_parser import PageParser

        parser = PageParser()
        registry = default_registry()

        parsed = parser.parse(SAMPLE_HTML_FULL, "https://example.com/sample-page")
        rule_data = parser.build_rule_data(parsed)
        results = registry.run_all(rule_data)

        page_summary = summarize_page(results)
        assert page_summary.total == 18
        assert page_summary.passed + page_summary.failed == 18
        assert 0 <= page_summary.pass_percentage <= 100

    def test_audit_normalization(self):
        """Test that a full audit report normalizes correctly."""
        from app.modules.category_check.core_seo.normalizer import AuditNormalizer

        report = AuditReport(
            audit_id="test-123",
            status="completed",
            total_pages=1,
            crawled_pages=1,
            pages_done=1,
            pages_failed=0,
            summary={
                "pages_total": 1,
                "pages_done": 1,
                "pages_failed": 0,
                "rules_passed": 17,
                "rules_failed": 1,
                "pass_percentage": 94.4,
            },
        )

        normalizer = AuditNormalizer()
        result = normalizer.normalize(report)
        assert result.audit_id == "test-123"
        assert result.status == "completed"
        assert result.summary["pass_percentage"] == 94.4
