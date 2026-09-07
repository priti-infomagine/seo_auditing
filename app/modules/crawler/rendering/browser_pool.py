"""
BrowserPool - Manages Playwright browser processes and isolated contexts safely.
"""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from app.core.logger import logger
from app.modules.crawler.config import CrawlConfig

try:
    from playwright.async_api import Browser, BrowserContext, Page, async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Browser = Any = object
    BrowserContext = Any = object
    Page = Any = object


class BrowserPool:
    """Singleton/Instance pool for Playwright Browser instances."""

    _instance: Optional["BrowserPool"] = None

    def __init__(self, config: Optional[CrawlConfig] = None):
        self.config = config or CrawlConfig()
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._semaphore = asyncio.Semaphore(self.config.browser_concurrency)
        self._lock = asyncio.Lock()
        self._concurrency_mismatch_warned: bool = False

    @classmethod
    def get_instance(cls, config: Optional[CrawlConfig] = None) -> "BrowserPool":
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    async def _ensure_browser(self) -> Optional[Browser]:
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
                    print('BROWSER LAUNCH ERROR:', repr(exc))
                    logger.error('Browser launch failed: %s', repr(exc))
                    self._browser = None
                    return None
            return self._browser

    @asynccontextmanager
    async def get_page(
        self, config: Optional[CrawlConfig] = None
    ) -> AsyncGenerator[Optional[Page], None]:
        """Acquire a browser page from the pool under concurrency limits.

        If *config* is supplied it overrides the singleton's frozen config for
        per-request values (user_agent, locale, browser_timeout).  The
        browser_concurrency semaphore capacity is **not** resized at runtime;
        a one-time warning is logged if a different value is requested.
        """
        if not PLAYWRIGHT_AVAILABLE:
            yield None
            return

        cfg = config or self.config

        if (
            cfg.browser_concurrency != self.config.browser_concurrency
            and not self._concurrency_mismatch_warned
        ):
            logger.warning(
                "BrowserPool: browser_concurrency=%d requested but this worker "
                "process's pool was initialized with %d; the original limit "
                "stays in effect until the worker process restarts.",
                cfg.browser_concurrency, self.config.browser_concurrency,
            )
            self._concurrency_mismatch_warned = True

        async with self._semaphore:
            browser = await self._ensure_browser()
            if not browser:
                print('BROWSER IS NONE after ensure')
                yield None
                return

            context: Optional[BrowserContext] = None
            page: Optional[Page] = None
            try:
                context = await browser.new_context(
                    user_agent=cfg.user_agent,
                    locale=cfg.accept_language.split(",")[0],
                    viewport={"width": 1280, "height": 800},
                )
                page = await context.new_page()
                page.set_default_timeout(cfg.browser_timeout * 1000)
                yield page
            except Exception as exc:
                print('CONTEXT ERROR:', repr(exc))
                logger.error('Browser context/page failed: %s', repr(exc))
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
