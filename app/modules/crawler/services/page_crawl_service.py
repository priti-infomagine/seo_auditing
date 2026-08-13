"""
Page crawl service - orchestrates fetching and initial processing of a single page.

Uses the fetcher protocol (HttpFetcher + BrowserFetcher) with RenderDetector
for dynamic Playwright fallback on SPA/CSR shells.
"""
from typing import Optional
from uuid import UUID

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.extractors.document_extractor import DocumentFacts, extract_document
from app.modules.crawler.fetchers.base import Fetcher
from app.modules.crawler.fetchers.browser_fetcher import BrowserFetcher
from app.modules.crawler.fetchers.http_fetcher import HttpFetcher
from app.modules.crawler.rendering.render_detector import RenderDetector
from app.modules.crawler.types import FetchResult, RenderResult
from app.shared.utils.url_utils import normalize_url


class PageCrawlResult:
    """Structured result of crawling a single page."""

    def __init__(
        self,
        url: str,
        normalized_url: str,
        document: Optional[DocumentFacts] = None,
        fetch_result: Optional[FetchResult] = None,
        error: Optional[str] = None,
        error_type: Optional[str] = None,
    ):
        self.url = url
        self.normalized_url = normalized_url
        self.document = document
        self.fetch_result = fetch_result
        self.error = error
        self.error_type = error_type
        self.success = document is not None and fetch_result is not None and error is None


class PageCrawlService:
    """Service for crawling a single page using dual fetcher protocol."""

    def __init__(
        self,
        http_fetcher: Optional[Fetcher] = None,
        browser_fetcher: Optional[Fetcher] = None,
        render_detector: Optional[RenderDetector] = None,
        config: Optional[CrawlConfig] = None,
    ):
        self.http_fetcher = http_fetcher or HttpFetcher(config=config)
        self.browser_fetcher = browser_fetcher or BrowserFetcher(config=config)
        self.render_detector = render_detector or RenderDetector()
        self.config = config or CrawlConfig()

    async def crawl_page(
        self,
        url: str,
        timeout: int = 30,
        follow_redirects: bool = True,
        user_agent: Optional[str] = None,
        max_redirects: int = 10,
        max_retries: int = 3,
    ) -> PageCrawlResult:
        """
        Crawl a single page and return structured result.

        Args:
            url: URL to crawl
            timeout: Request timeout in seconds
            follow_redirects: Whether to follow redirects
            user_agent: User agent string
            max_redirects: Maximum redirects to follow
            max_retries: Maximum retry attempts

        Returns:
            PageCrawlResult with document facts or error
        """
        try:
            normalized_url = normalize_url(url)
        except Exception as exc:
            return PageCrawlResult(
                url=url,
                normalized_url=url,
                error=str(exc),
                error_type="invalid_url",
            )

        req_timeout = timeout if timeout is not None else self.config.request_timeout
        headers = {}
        if user_agent:
            headers["User-Agent"] = user_agent

        fetch_result = await self.http_fetcher.fetch(
            normalized_url,
            timeout=req_timeout,
            headers=headers if headers else None,
        )

        html_content = fetch_result.content.decode("utf-8", errors="replace")

        if fetch_result.success and self.config.enable_browser_rendering:
            needs_render, reason = self.render_detector.needs_browser_render(fetch_result)
            if needs_render:
                render_result = await self.browser_fetcher.fetch(
                    normalized_url,
                    timeout=req_timeout,
                    headers=headers if headers else None,
                )
                if render_result.success and render_result.html:
                    html_content = render_result.html
                    fetch_result = _merge_render_into_fetch(fetch_result, render_result)

        if fetch_result.error:
            return PageCrawlResult(
                url=url,
                normalized_url=normalized_url,
                fetch_result=fetch_result,
                error=fetch_result.error,
                error_type=fetch_result.error_type,
            )

        document = extract_document(html_content, normalized_url)

        return PageCrawlResult(
            url=url,
            normalized_url=normalized_url,
            document=document,
            fetch_result=fetch_result,
        )


def _merge_render_into_fetch(fetch: FetchResult, render: RenderResult) -> FetchResult:
    """Merge browser render result into the original HTTP fetch result."""
    fetch.content = render.html.encode("utf-8")
    fetch.content_type = "text/html"
    fetch.content_length = len(fetch.content)
    fetch.final_url = render.final_url or fetch.final_url
    fetch.render_mode = "browser"
    fetch.render_reason = render.render_reason
    if render.status_code:
        fetch.status_code = render.status_code
    return fetch
