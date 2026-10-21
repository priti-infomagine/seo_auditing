"""
BrowserManager — Playwright + Chromium browser lifecycle manager.

Singleton browser instance with bounded concurrency via semphore.
Gracefully degrades if Playwright is not installed.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from app.core.logger import logger

from .config import CoreSEOConfig

try:
    from playwright.async_api import Browser, BrowserContext, Page, async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Browser = Any  # type: ignore[misc,assignment]
    BrowserContext = Any  # type: ignore[misc,assignment]
    Page = Any  # type: ignore[misc,assignment]
    async_playwright = None  # type: ignore[assignment]


class BrowserUnavailableError(RuntimeError):
    """Raised when the browser is unavailable (Playwright or Chromium not installed)."""



class BrowserManager:
    """Singleton Playwright browser manager.

    Manages a single browser instance with per-page context isolation
    and bounded concurrency via an asyncio.Semaphore.
    """

    _instance: BrowserManager | None = None

    def __init__(self, config: CoreSEOConfig | None = None):
        self.config = config or CoreSEOConfig()
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._semaphore = asyncio.Semaphore(self.config.browser_concurrency)
        self._lock = asyncio.Lock()
        self._concurrency_mismatch_warned: bool = False
        self._available: bool = PLAYWRIGHT_AVAILABLE

    @classmethod
    def get_instance(cls, config: CoreSEOConfig | None = None) -> BrowserManager:
        """Get or create the singleton BrowserManager instance."""
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (useful for tests)."""
        cls._instance = None

    async def _ensure_browser(self) -> Browser | None:
        """Lazily initialize the Playwright browser. Returns None if unavailable."""
        if not PLAYWRIGHT_AVAILABLE:
            return None

        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                try:
                    self._playwright = await async_playwright().start()
                    self._browser = await self._playwright.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                        ],
                    )
                except Exception as exc:
                    logger.error("Browser launch failed: %s", repr(exc))
                    self._browser = None
                    return None
            return self._browser

    @property
    def is_available(self) -> bool:
        """Whether Playwright is installed and available."""
        return self._available

    @asynccontextmanager
    async def get_page(
        self, config: CoreSEOConfig | None = None
    ) -> AsyncGenerator[Page | None, None]:
        """Acquire a browser page under concurrency limits.

        If *config* is supplied it overrides the singleton's config for
        per-request values (user_agent, locale, viewport, browser_timeout).

        Yields ``None`` if Playwright is not available or browser acquisition fails.
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright is not installed; browser rendering unavailable")
            yield None
            return

        cfg = config or self.config

        if (
            cfg.browser_concurrency != self.config.browser_concurrency
            and not self._concurrency_mismatch_warned
        ):
            logger.warning(
                "BrowserManager: browser_concurrency=%d requested but this worker "
                "process's manager was initialized with %d; the original limit "
                "stays in effect until the worker process restarts.",
                cfg.browser_concurrency,
                self.config.browser_concurrency,
            )
            self._concurrency_mismatch_warned = True

        async with self._semaphore:
            browser = await self._ensure_browser()
            if not browser:
                yield None
                return

            context: BrowserContext | None = None
            page: Page | None = None
            try:
                context = await browser.new_context(
                    user_agent=cfg.user_agent,
                    locale=cfg.accept_language.split(",")[0],
                    viewport={"width": cfg.viewport_width, "height": cfg.viewport_height},
                )
                page = await context.new_page()
                page.set_default_timeout(cfg.browser_timeout * 1000)
                yield page
            except Exception as exc:
                logger.error("Browser context/page creation failed: %s", repr(exc))
                yield None
            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass

    async def close(self) -> None:
        """Shutdown browser and playwright processes gracefully."""
        async with self._lock:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None


__all__ = ["PLAYWRIGHT_AVAILABLE", "BrowserManager", "BrowserUnavailableError"]
