"""
Page crawl service - orchestrates fetching and initial processing of a single page.

Uses the fetcher protocol (HttpFetcher + BrowserFetcher) with RenderDetector
for dynamic Playwright fallback on SPA/CSR shells.

Initial HTTP evidence is preserved separately from the final result so
callers can compare pre-render and post-render responses without
corrupting redirect/final_url data.
"""
from typing import Optional
from uuid import UUID
from functools import partial
import asyncio

from app.core.logger import logger
from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.extractors.document_extractor import create_document_facts, DocumentFacts
from app.modules.crawler.fetchers.base import Fetcher
from app.modules.crawler.fetchers.browser_fetcher import BrowserFetcher
from app.modules.crawler.fetchers.http_fetcher import HttpFetcher
from app.modules.crawler.rendering.render_detector import RenderDetector
from app.modules.crawler.types import FetchResult, RedirectInfo
from app.modules.crawler.utils.thread_pool import cpu_bound_executor
from app.shared.utils.url_utils import normalize_url


class PageCrawlResult:
    """Structured result of crawling a single page."""

    def __init__(
        self,
        url: str,
        normalized_url: str,
        document: Optional[DocumentFacts] = None,
        fetch_result: Optional[FetchResult] = None,
        initial_fetch_result: Optional[FetchResult] = None,
        error: Optional[str] = None,
        error_type: Optional[str] = None,
    ):
        self.url = url
        self.normalized_url = normalized_url
        self.document = document
        self.fetch_result = fetch_result
        self.initial_fetch_result = initial_fetch_result
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
            PageCrawlResult with document facts or error.
            If browser fallback occurred, fetch_result contains the merged
            browser result and initial_fetch_result contains the original
            HTTP response.
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

        # 1. HTTP fetch first
        http_result = await self.http_fetcher.fetch(
            normalized_url,
            timeout=req_timeout,
            headers=headers if headers else None,
        )
        initial_fetch_result = http_result
        html_content = http_result.content.decode("utf-8", errors="replace")

        # 2. Rendering decision (only for successful HTML responses)
        if http_result.success and self.config.enable_browser_rendering:
            loop = asyncio.get_running_loop()
            decision = await loop.run_in_executor(
                cpu_bound_executor,
                partial(self.render_detector.evaluate, http_result),
            )
            if decision.needs_render:
                try:
                    browser_result = await self.browser_fetcher.fetch(
                        normalized_url,
                        timeout=req_timeout,
                        headers=headers if headers else None,
                    )
                    if browser_result.success and browser_result.content:
                        html_content = browser_result.content.decode("utf-8", errors="replace")
                        http_result = _merge_render_into_fetch(initial_fetch_result, browser_result)
                    else:
                        logger.warning(
                            "Browser fallback failed for %s: %s",
                            normalized_url,
                            browser_result.error or "no content returned",
                        )
                except Exception as browser_exc:
                    logger.warning(
                        "Browser fallback exception for %s: %s",
                        normalized_url,
                        browser_exc,
                    )
                # If browser fallback fails, http_result remains the initial HTTP result

        # 3. Error handling
        if http_result.error:
            return PageCrawlResult(
                url=url,
                normalized_url=normalized_url,
                fetch_result=http_result,
                initial_fetch_result=initial_fetch_result if initial_fetch_result.error else None,
                error=http_result.error,
                error_type=http_result.error_type,
            )

        # 4. Build minimal document facts (extraction happens via parser module)
        document = create_document_facts(html_content, normalized_url)

        return PageCrawlResult(
            url=url,
            normalized_url=normalized_url,
            document=document,
            fetch_result=http_result,
            initial_fetch_result=initial_fetch_result,
        )


def _merge_render_into_fetch(initial: FetchResult, browser: FetchResult) -> FetchResult:
    """
    Merge browser fallback result into initial HTTP result.

    Preserves initial HTTP evidence (redirect_chain, url, normalized_url)
    while replacing content with browser-rendered bytes.
    """
    return FetchResult(
        url=initial.url,
        normalized_url=initial.normalized_url,
        status_code=browser.status_code or initial.status_code,
        content=browser.content,
        headers=browser.headers or initial.headers,
        final_url=browser.final_url or initial.final_url,
        content_type="text/html",
        content_length=len(browser.content),
        response_time_ms=initial.response_time_ms + browser.response_time_ms,
        redirect_chain=initial.redirect_chain,
        success=True,
        error=None,
        error_type=None,
        render_mode="browser",
        render_reason=browser.render_reason,
    )
