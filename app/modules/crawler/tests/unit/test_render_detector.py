"""
Tests for RenderDetector SPA/low-content signal detection.
"""
import pytest

from app.modules.crawler.rendering.render_detector import RenderDetector
from app.modules.crawler.types import FetchResult


def _make_fetch_result(content_type: str = "text/html", content: bytes = b"<html><body>Hello</body></html>") -> FetchResult:
    return FetchResult(
        url="https://example.com/page",
        normalized_url="https://example.com/page",
        status_code=200,
        content=content,
        headers={"content-type": content_type},
        final_url="https://example.com/page",
        content_type=content_type,
        content_length=len(content),
        response_time_ms=100,
        redirect_chain=[],
        success=True,
        render_mode="http",
    )


class TestRenderDetector:
    def test_sufficient_content_no_render(self):
        detector = RenderDetector()
        html = b"<html><head><title>Page</title></head><body>" + b" ".join([b"word"] * 30) + b"</body></html>"
        result = detector.needs_browser_render(_make_fetch_result(content=html))
        assert result[0] is False

    def test_spa_root_element_triggers_render(self):
        detector = RenderDetector()
        html = b'<html><body><div id="root"></div></body></html>'
        result = detector.needs_browser_render(_make_fetch_result(content=html))
        assert result[0] is True

    def test_low_word_count_triggers_render(self):
        detector = RenderDetector(min_word_count=50)
        html = b"<html><body><p>Hi</p></body></html>"
        result = detector.needs_browser_render(_make_fetch_result(content=html))
        assert result[0] is True

    def test_non_html_does_not_render(self):
        detector = RenderDetector()
        result = detector.needs_browser_render(_make_fetch_result(content_type="application/json"))
        assert result[0] is False
