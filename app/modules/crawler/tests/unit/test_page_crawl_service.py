"""
Tests for PageCrawlService result preservation and browser fallback.

Verifies:
- Initial HTTP result is preserved in PageCrawlResult.initial_fetch_result
- Browser fallback merges content without corrupting redirect_chain/final_url
- No browser fallback when HTML is sufficient
- No browser fallback on HTTP failure
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.rendering.render_detector import RenderDetector
from app.modules.crawler.services.page_crawl_service import PageCrawlService, PageCrawlResult
from app.modules.crawler.types import FetchResult, RedirectInfo, RenderDecision


def _make_http_fetch_result(url="https://example.com/page", content=b"<html><body>Hello</body></html>"):
    return FetchResult(
        url=url,
        normalized_url=url,
        status_code=200,
        content=content,
        headers={"content-type": "text/html"},
        final_url=url,
        content_type="text/html",
        content_length=len(content),
        response_time_ms=100,
        redirect_chain=[],
        success=True,
        render_mode="http",
    )


def _make_browser_fetch_result(url="https://example.com/page", content=b"<html><body>Rendered</body></html>"):
    return FetchResult(
        url=url,
        normalized_url=url,
        status_code=200,
        content=content,
        headers={"content-type": "text/html"},
        final_url=url,
        content_type="text/html",
        content_length=len(content),
        response_time_ms=500,
        redirect_chain=[],
        success=True,
        render_mode="browser",
        render_reason="application_shell",
    )


class TestPageCrawlService:
    @pytest.mark.asyncio
    async def test_http_only_when_sufficient(self):
        http_fetcher = AsyncMock()
        http_fetcher.fetch = AsyncMock(return_value=_make_http_fetch_result())
        browser_fetcher = AsyncMock()
        browser_fetcher.fetch = AsyncMock()

        service = PageCrawlService(
            http_fetcher=http_fetcher,
            browser_fetcher=browser_fetcher,
            render_detector=RenderDetector(),
            config=CrawlConfig(enable_browser_rendering=True),
        )
        result = await service.crawl_page("https://example.com/page")

        assert result.success is True
        assert result.fetch_result.render_mode == "http"
        assert result.initial_fetch_result is not None
        assert result.initial_fetch_result.render_mode == "http"
        browser_fetcher.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_browser_fallback_when_shell(self):
        shell_html = b"<html><body><div id=\"root\"></div></body></html>"
        http_result = _make_http_fetch_result(content=shell_html)
        browser_result = _make_browser_fetch_result()

        http_fetcher = AsyncMock()
        http_fetcher.fetch = AsyncMock(return_value=http_result)
        browser_fetcher = AsyncMock()
        browser_fetcher.fetch = AsyncMock(return_value=browser_result)

        service = PageCrawlService(
            http_fetcher=http_fetcher,
            browser_fetcher=browser_fetcher,
            render_detector=RenderDetector(),
            config=CrawlConfig(enable_browser_rendering=True),
        )
        result = await service.crawl_page("https://example.com/page")

        assert result.success is True
        assert result.fetch_result.render_mode == "browser"
        assert result.fetch_result.content == browser_result.content
        assert result.initial_fetch_result is not None
        assert result.initial_fetch_result.render_mode == "http"
        assert result.initial_fetch_result.content == shell_html
        browser_fetcher.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_browser_fallback_failure_preserves_http(self):
        shell_html = b"<html><body><div id=\"root\"></div></body></html>"
        http_result = _make_http_fetch_result(content=shell_html)
        failed_browser = FetchResult(
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
            error="playwright_error",
            error_type="browser_render_error",
            render_mode="browser",
        )

        http_fetcher = AsyncMock()
        http_fetcher.fetch = AsyncMock(return_value=http_result)
        browser_fetcher = AsyncMock()
        browser_fetcher.fetch = AsyncMock(return_value=failed_browser)

        service = PageCrawlService(
            http_fetcher=http_fetcher,
            browser_fetcher=browser_fetcher,
            render_detector=RenderDetector(),
            config=CrawlConfig(enable_browser_rendering=True),
        )
        result = await service.crawl_page("https://example.com/page")

        assert result.fetch_result is http_result
        assert result.initial_fetch_result is http_result
        assert result.fetch_result.render_mode == "http"

    @pytest.mark.asyncio
    async def test_merge_preserves_redirect_chain(self):
        shell_html = b"<html><body><div id=\"root\"></div></body></html>"
        http_result = _make_http_fetch_result(content=shell_html)
        http_result.redirect_chain = [
            RedirectInfo(url="http://example.com/page", status_code=301, location="https://example.com/page"),
        ]
        browser_result = _make_browser_fetch_result()

        http_fetcher = AsyncMock()
        http_fetcher.fetch = AsyncMock(return_value=http_result)
        browser_fetcher = AsyncMock()
        browser_fetcher.fetch = AsyncMock(return_value=browser_result)

        service = PageCrawlService(
            http_fetcher=http_fetcher,
            browser_fetcher=browser_fetcher,
            render_detector=RenderDetector(),
            config=CrawlConfig(enable_browser_rendering=True),
        )
        result = await service.crawl_page("https://example.com/page")

        assert len(result.fetch_result.redirect_chain) == 1
        assert result.fetch_result.redirect_chain[0].url == "http://example.com/page"

    @pytest.mark.asyncio
    async def test_merge_preserves_final_url(self):
        shell_html = b"<html><body><div id=\"root\"></div></body></html>"
        http_result = _make_http_fetch_result(content=shell_html)
        http_result.final_url = "https://www.example.com/page"
        browser_result = _make_browser_fetch_result()

        http_fetcher = AsyncMock()
        http_fetcher.fetch = AsyncMock(return_value=http_result)
        browser_fetcher = AsyncMock()
        browser_fetcher.fetch = AsyncMock(return_value=browser_result)

        service = PageCrawlService(
            http_fetcher=http_fetcher,
            browser_fetcher=browser_fetcher,
            render_detector=RenderDetector(),
            config=CrawlConfig(enable_browser_rendering=True),
        )
        result = await service.crawl_page("https://example.com/page")

        # Should use browser final_url if available, otherwise initial
        assert result.fetch_result.final_url == browser_result.final_url

    @pytest.mark.asyncio
    async def test_http_failure_no_browser_fallback(self):
        http_result = FetchResult(
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

        http_fetcher = AsyncMock()
        http_fetcher.fetch = AsyncMock(return_value=http_result)
        browser_fetcher = AsyncMock()
        browser_fetcher.fetch = AsyncMock()

        service = PageCrawlService(
            http_fetcher=http_fetcher,
            browser_fetcher=browser_fetcher,
            render_detector=RenderDetector(),
            config=CrawlConfig(enable_browser_rendering=True),
        )
        result = await service.crawl_page("https://example.com/page")

        assert result.error == "timeout"
        assert result.fetch_result is http_result
        browser_fetcher.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_render_detector_evaluate_offloaded_to_thread(self):
        """RenderDetector.evaluate must be called via run_in_executor, not inline."""
        mock_detector = MagicMock()
        mock_detector.evaluate.return_value = RenderDecision(
            False, "initial_html_sufficient"
        )

        http_fetcher = AsyncMock()
        http_fetcher.fetch = AsyncMock(return_value=_make_http_fetch_result())
        browser_fetcher = AsyncMock()
        browser_fetcher.fetch = AsyncMock()

        service = PageCrawlService(
            http_fetcher=http_fetcher,
            browser_fetcher=browser_fetcher,
            render_detector=mock_detector,
            config=CrawlConfig(enable_browser_rendering=True),
        )

        loop = asyncio.get_running_loop()
        with patch.object(
            loop, "run_in_executor", wraps=loop.run_in_executor
        ) as mock_exec:
            result = await service.crawl_page("https://example.com/page")

        mock_detector.evaluate.assert_called_once()
        mock_exec.assert_called_once()  # confirms offload, not inline call
        assert result.success is True
