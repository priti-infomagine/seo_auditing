"""
Tests for RenderDetector rendering-sufficiency checks.

RenderDetector must NOT trigger Playwright for SEO deficiencies
(missing title, H1, meta description, low word count for SEO reasons).
It must ONLY trigger when the HTML is clearly an incomplete client-side shell.
"""
import pytest

from app.modules.crawler.rendering.render_detector import RenderDetector
from app.modules.crawler.types import FetchResult


def _make_fetch_result(content_type="text/html", content=b"<html><body>Hello world</body></html>"):
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
    def test_empty_shell_triggers_render(self):
        detector = RenderDetector()
        html = b"<html><body><div id=\"root\"></div></body></html>"
        decision = detector.evaluate(_make_fetch_result(content=html))
        assert decision.needs_render is True
        assert decision.reason == "application_shell"

    def test_loading_placeholder_triggers_render(self):
        detector = RenderDetector()
        html = b"<html><body>Loading...</body></html>"
        decision = detector.evaluate(_make_fetch_result(content=html))
        assert decision.needs_render is True
        assert decision.reason == "loading_placeholder"

    def test_low_content_density_triggers_render(self):
        detector = RenderDetector(min_word_count=10, min_text_ratio=0.01)
        # Very little text but large HTML overhead (scripts/styles)
        html = b"<html><head><script>" + b"x" * 200 + b"</script></head><body><p>Hi</p></body></html>"
        decision = detector.evaluate(_make_fetch_result(content=html))
        assert decision.needs_render is True
        assert decision.reason == "low_content"

    def test_complete_ssr_page_sufficient(self):
        detector = RenderDetector()
        html = (
            b"<html><head><title>Page</title></head><body>"
            b"<h1>Welcome</h1><p>This is a complete SSR page with enough content.</p>"
            b"<a href=\"/about\">About</a></body></html>"
        )
        decision = detector.evaluate(_make_fetch_result(content=html))
        assert decision.needs_render is False
        assert decision.reason == "initial_html_sufficient"

    def test_react_markers_with_content_sufficient(self):
        detector = RenderDetector()
        html = (
            b"<html><head><title>React App</title></head><body>"
            b"<div id=\"root\"><h1>Hello</h1><p>Content loaded.</p></div>"
            b"<script src=\"https://unpkg.com/react@18/umd/react.production.min.js\"></script>"
            b"</body></html>"
        )
        decision = detector.evaluate(_make_fetch_result(content=html))
        assert decision.needs_render is False
        assert decision.reason == "initial_html_sufficient"

    def test_not_html_does_not_trigger(self):
        detector = RenderDetector()
        decision = detector.evaluate(_make_fetch_result(content_type="application/json"))
        assert decision.needs_render is False
        assert decision.reason == "not_html"

    def test_http_failure_does_not_trigger(self):
        detector = RenderDetector()
        failed = FetchResult(
            url="https://example.com/page",
            normalized_url="https://example.com/page",
            status_code=0,
            content=b"",
            headers={},
            final_url="https://example.com/page",
            content_type=None,
            content_length=0,
            response_time_ms=0,
            redirect_chain=[],
            success=False,
            error="timeout",
            error_type="timeout",
            render_mode="http",
        )
        decision = detector.evaluate(failed)
        assert decision.needs_render is False
        assert decision.reason == "http_fetch_failed"

    def test_missing_title_does_not_trigger_render(self):
        detector = RenderDetector()
        html = b"<html><body><h1>Hello</h1><p>Real content here with enough words.</p></body></html>"
        decision = detector.evaluate(_make_fetch_result(content=html))
        assert decision.needs_render is False
        assert decision.reason == "initial_html_sufficient"

    def test_needs_browser_render_backward_compat(self):
        detector = RenderDetector()
        html = b"<html><body><div id=\"root\"></div></body></html>"
        needs_render, reason = detector.needs_browser_render(_make_fetch_result(content=html))
        assert needs_render is True
        assert reason == "application_shell"
