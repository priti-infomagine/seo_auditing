"""
Unit tests for BrowserPool.

Verifies:
- get_page(config) uses the passed config's user_agent/locale/timeout,
  not the singleton's self.config
- get_page() without config falls back to self.config (backward compat)
- Concurrency mismatch warning fires once, not per-page
- No warning when browser_concurrency matches
"""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.rendering.browser_pool import BrowserPool


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure each test starts with a clean BrowserPool singleton."""
    BrowserPool._instance = None
    yield
    BrowserPool._instance = None


def _make_mock_playwright_chain():
    """Create a fully-mocked Playwright browser chain.

    Returns (mock_browser, mock_context, mock_page) so callers can assert
    on call arguments after the async context manager exits.
    """
    mock_page = MagicMock()
    mock_page.set_default_timeout = MagicMock()
    mock_page.close = AsyncMock()

    mock_context = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.close = AsyncMock()

    mock_browser = MagicMock()
    mock_browser.is_connected = MagicMock(return_value=True)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    mock_chromium = MagicMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_playwright = MagicMock()
    mock_playwright.chromium = mock_chromium
    mock_playwright.stop = AsyncMock()

    mock_pw_builder = MagicMock()
    mock_pw_builder.start = AsyncMock(return_value=mock_playwright)

    return mock_browser, mock_context, mock_page, mock_pw_builder


def _patch_playwright():
    """Return a patcher for async_playwright in the browser_pool module.

    The mock chain is set up so that:
    async_playwright() → builder with .start() → playwright with .chromium.launch()
    → mock_browser with .is_connected() → True, .new_context() → mock_context,
    .new_page() → mock_page.
    """
    mock_browser, mock_context, mock_page, mock_pw_builder = _make_mock_playwright_chain()
    return patch(
        "app.modules.crawler.rendering.browser_pool.async_playwright",
        return_value=mock_pw_builder,
    ), mock_browser, mock_context, mock_page


class TestBrowserPool:
    @pytest.mark.asyncio
    async def test_get_page_uses_passed_config_not_singleton(self):
        """get_page(config) must use the passed config's settings, not self.config."""
        patcher, mock_browser, mock_context, mock_page = _patch_playwright()
        with patcher:
            config1 = CrawlConfig(
                user_agent="UA-Original",
                accept_language="en-US,en;q=0.9",
                browser_timeout=30.0,
                browser_concurrency=2,
            )
            pool = BrowserPool(config1)

            config2 = CrawlConfig(
                user_agent="UA-Override",
                accept_language="fr-FR,fr;q=0.9",
                browser_timeout=60.0,
                browser_concurrency=2,
            )

            async with pool.get_page(config2) as page:
                pass

            mock_browser.new_context.assert_called_once()
            call_kwargs = mock_browser.new_context.call_args.kwargs
            assert call_kwargs["user_agent"] == "UA-Override"
            assert call_kwargs["locale"] == "fr-FR"
            mock_page.set_default_timeout.assert_called_once_with(60000)

    @pytest.mark.asyncio
    async def test_get_page_falls_back_to_self_config(self):
        """get_page() without config uses the singleton's self.config."""
        patcher, mock_browser, mock_context, mock_page = _patch_playwright()
        with patcher:
            config1 = CrawlConfig(
                user_agent="UA-Default",
                accept_language="de-DE,de;q=0.9",
                browser_timeout=45.0,
                browser_concurrency=3,
            )
            pool = BrowserPool(config1)

            async with pool.get_page() as page:
                pass

            mock_browser.new_context.assert_called_once()
            call_kwargs = mock_browser.new_context.call_args.kwargs
            assert call_kwargs["user_agent"] == "UA-Default"
            assert call_kwargs["locale"] == "de-DE"
            mock_page.set_default_timeout.assert_called_once_with(45000)

    @pytest.mark.asyncio
    async def test_concurrency_mismatch_warns_once(self, caplog):
        """Warning fires once when browser_concurrency differs, not per-page."""
        patcher, mock_browser, mock_context, mock_page = _patch_playwright()
        with patcher:
            config1 = CrawlConfig(
                user_agent="UA-1",
                accept_language="en-US,en;q=0.9",
                browser_timeout=30.0,
                browser_concurrency=2,
            )
            pool = BrowserPool(config1)

            config2 = CrawlConfig(
                user_agent="UA-2",
                accept_language="en-US,en;q=0.9",
                browser_timeout=30.0,
                browser_concurrency=5,
            )
            with caplog.at_level(logging.WARNING, logger="app"):
                async with pool.get_page(config2) as page:
                    pass

            assert any(
                "browser_concurrency=5 requested but this worker process"
                in rec.message
                for rec in caplog.records
            )
            assert pool._concurrency_mismatch_warned is True

            # Second call — same pool, different concurrency — should NOT warn again
            caplog.clear()
            config3 = CrawlConfig(
                user_agent="UA-3",
                accept_language="en-US,en;q=0.9",
                browser_timeout=30.0,
                browser_concurrency=3,
            )
            async with pool.get_page(config3) as page:
                pass
            assert not any(
                "browser_concurrency" in rec.message
                for rec in caplog.records
            ), "Warning should not fire again after first time"

    @pytest.mark.asyncio
    async def test_same_concurrency_no_warning(self, caplog):
        """No warning when browser_concurrency matches."""
        patcher, mock_browser, mock_context, mock_page = _patch_playwright()
        with patcher:
            config1 = CrawlConfig(
                user_agent="UA-1",
                accept_language="en-US,en;q=0.9",
                browser_timeout=30.0,
                browser_concurrency=4,
            )
            pool = BrowserPool(config1)

            config2 = CrawlConfig(
                user_agent="UA-2",
                accept_language="en-US,en;q=0.9",
                browser_timeout=30.0,
                browser_concurrency=4,
            )
            with caplog.at_level(logging.WARNING, logger="app"):
                async with pool.get_page(config2) as page:
                    pass

            assert not any(
                "browser_concurrency" in rec.message
                for rec in caplog.records
            ), "No warning should fire when concurrency matches"
            assert pool._concurrency_mismatch_warned is False
