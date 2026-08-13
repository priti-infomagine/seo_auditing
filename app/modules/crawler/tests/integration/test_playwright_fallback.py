"""
Integration test for Playwright render fallback when static fetch has insufficient content.
"""
import pytest

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.rendering.render_detector import RenderDetector
from app.modules.crawler.types import FetchResult


class TestPlaywrightFallback:
    def test_low_content_triggers_fallback(self):
        config = CrawlConfig(http_concurrency=10, browser_concurrency=2, enable_browser_rendering=True)
        detector = RenderDetector()
        html = b"<html><head><title>Page</title></head><body><p>Hi</p></body></html>"
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
        needs_render, reason = detector.needs_browser_render(fetch)
        assert needs_render is True
        assert "low_word_count" in reason or "small_html_shell" in reason
