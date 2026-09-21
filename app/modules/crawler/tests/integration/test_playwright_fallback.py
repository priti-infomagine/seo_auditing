"""
Integration test for Playwright render fallback when static fetch has insufficient content.
"""
import pytest

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.rendering.render_detector import RenderDetector
from app.modules.crawler.types import FetchResult


class TestPlaywrightFallback:
    def test_empty_shell_triggers_fallback(self):
        config = CrawlConfig(http_concurrency=10, browser_concurrency=2, enable_browser_rendering=True)
        detector = RenderDetector()
        html = b"<html><body><div id=\"root\"></div></body></html>"
        fetch = FetchResult(
            url="https://example.com/page",
            normalized_url="https://example.com/page",
            status_code=200,
            content=html,
            headers={"content-type": "text/html"},
            final_url="https://example.com/page",
            content_type="text/html",
            content_length=len(html),
            response_time_ms=100,
            redirect_chain=[],
            success=True,
            render_mode="http",
        )
        decision = detector.evaluate(fetch)
        assert decision.needs_render is True
        assert decision.reason == "application_shell"

    def test_complete_ssr_page_does_not_trigger_fallback(self):
        config = CrawlConfig(http_concurrency=10, browser_concurrency=2, enable_browser_rendering=True)
        detector = RenderDetector()
        html = (
            b"<html><head><title>Page</title></head><body>"
            b"<h1>Welcome</h1><p>This is a complete SSR page with enough content.</p>"
            b"<a href=\"/about\">About</a></body></html>"
        )
        fetch = FetchResult(
            url="https://example.com/page",
            normalized_url="https://example.com/page",
            status_code=200,
            content=html,
            headers={"content-type": "text/html"},
            final_url="https://example.com/page",
            content_type="text/html",
            content_length=len(html),
            response_time_ms=100,
            redirect_chain=[],
            success=True,
            render_mode="http",
        )
        decision = detector.evaluate(fetch)
        assert decision.needs_render is False
        assert decision.reason == "initial_html_sufficient"
