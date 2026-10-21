"""
Crawler — Core crawler that fetches + renders pages via Playwright.

Each page is treated as a Celery task (crawl → parse → rule-check → score
→ normalize). This module handles only the crawl step: acquiring a browser
page, navigating to the URL, waiting for the page to settle, and capturing
the rendered HTML + metadata into a CrawlResult.
"""
from __future__ import annotations

import time
from typing import Any

from app.core.logger import logger

from .browser_manager import BrowserManager, BrowserUnavailableError
from .config import CoreSEOConfig
from .models import CrawlResult


class Crawler:
    """Core crawler: fetch + render via Playwright Chromium.

    Uses dependency injection for BrowserManager and CoreSEOConfig so
    it is fully testable with mocks.
    """

    def __init__(
        self,
        browser_manager: BrowserManager | None = None,
        config: CoreSEOConfig | None = None,
    ):
        self.config = config or CoreSEOConfig()
        self._browser_manager = browser_manager

    @property
    def browser_manager(self) -> BrowserManager:
        if self._browser_manager is None:
            self._browser_manager = BrowserManager.get_instance(self.config)
        return self._browser_manager

    @browser_manager.setter
    def browser_manager(self, value: BrowserManager) -> None:
        self._browser_manager = value

    async def crawl(self, url: str) -> CrawlResult:
        """Crawl a single URL: render via Playwright, capture HTML + metadata.

        Args:
            url: Normalized URL to crawl.

        Returns:
            CrawlResult with html, status_code, headers, final_url, timing,
            and error info (error set + success=False on failure).
        """
        start_time = time.perf_counter()

        if not self.browser_manager.is_available:
            raise BrowserUnavailableError(
                "Playwright is not installed; cannot crawl URL"
            )

        console_errors: list[str] = []
        js_errors: list[str] = []
        failed_requests: list[dict[str, Any]] = []
        status_code = 0
        response_headers: dict[str, str] = {}

        try:
            async with self.browser_manager.get_page(self.config) as page:
                if page is None:
                    return CrawlResult(
                        url=url,
                        error="Could not acquire browser page",
                        success=False,
                        response_time_ms=int((time.perf_counter() - start_time) * 1000),
                    )

                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                page.on("pageerror", lambda exc: js_errors.append(str(exc)))
                page.on(
                    "requestfailed",
                    lambda req: failed_requests.append(
                        {
                            "url": req.url,
                            "failure": req.failure.error_text
                            if (req.failure and hasattr(req.failure, "error_text"))
                            else (str(req.failure) if req.failure else "unknown"),
                        }
                    ),
                )

                try:
                    response = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self.config.browser_timeout * 1000,
                    )
                    if response:
                        status_code = response.status
                        try:
                            all_headers = await response.all_headers()
                            response_headers = {k.lower(): v for k, v in all_headers.items()}
                        except Exception:
                            response_headers = {}

                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass

                    html = await page.content()
                    final_url = page.url

                    response_time_ms = int((time.perf_counter() - start_time) * 1000)
                    return CrawlResult(
                        url=url,
                        html=html,
                        status_code=status_code,
                        headers=response_headers,
                        response_time_ms=response_time_ms,
                        final_url=final_url,
                        console_errors=console_errors,
                        js_errors=js_errors,
                        failed_requests=failed_requests,
                        success=True,
                    )

                except Exception as exc:
                    response_time_ms = int((time.perf_counter() - start_time) * 1000)
                    logger.error("Browser page.goto failed for %s: %s", url, repr(exc))
                    return CrawlResult(
                        url=url,
                        error=str(exc),
                        success=False,
                        console_errors=console_errors,
                        js_errors=js_errors,
                        failed_requests=failed_requests,
                        response_time_ms=response_time_ms,
                    )

        except Exception as exc:
            response_time_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error("Crawler.crawl() error for %s: %s", url, repr(exc))
            return CrawlResult(
                url=url,
                error=str(exc),
                success=False,
                response_time_ms=response_time_ms,
            )


__all__ = ["BrowserUnavailableError", "Crawler"]
