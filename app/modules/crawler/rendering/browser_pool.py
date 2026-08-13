"""
BrowserPool - Manages Playwright browser processes and isolated contexts safely.
"""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

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
                except Exception:
                    self._browser = None
            return self._browser

    @asynccontextmanager
    async def get_page(self) -> AsyncGenerator[Optional[Page], None]:
        """Acquire a browser page from the pool under concurrency limits."""
        if not PLAYWRIGHT_AVAILABLE:
            yield None
            return

        async with self._semaphore:
            browser = await self._ensure_browser()
            if not browser:
                yield None
                return

            context: Optional[BrowserContext] = None
            page: Optional[Page] = None
            try:
                context = await browser.new_context(
                    user_agent=self.config.user_agent,
                    locale=self.config.accept_language.split(",")[0],
                    viewport={"width": 1280, "height": 800},
                )
                page = await context.new_page()
                page.set_default_timeout(self.config.browser_timeout * 1000)
                yield page
            except Exception:
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
