"""
Tests for HttpFetcher connection pooling.

Verifies that a single httpx.AsyncClient is created per HttpFetcher instance,
reused across fetch calls, and properly closed.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.fetchers.http_fetcher import HttpFetcher


class TestHttpFetcherPooling:
    def test_single_client_created(self):
        fetcher = HttpFetcher()
        assert fetcher._client is not None
        # Ensure it is an httpx AsyncClient
        import httpx
        assert isinstance(fetcher._client, httpx.AsyncClient)

    @pytest.mark.asyncio
    async def test_fetch_reuses_client(self):
        fetcher = HttpFetcher()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = "https://example.com/page"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.content = b"<html><body>Hello</body></html>"
        mock_response.history = []

        with patch.object(fetcher._client, "get", new_callable=AsyncMock, return_value=mock_response) as mock_get:
            result = await fetcher.fetch("https://example.com/page")
            assert result.success is True
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_cleans_up(self):
        fetcher = HttpFetcher()
        with patch.object(fetcher._client, "aclose", new_callable=AsyncMock) as mock_close:
            await fetcher.close()
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_aenter_aexit(self):
        fetcher = HttpFetcher()
        with patch.object(fetcher._client, "aclose", new_callable=AsyncMock) as mock_close:
            async with fetcher:
                assert fetcher._client is not None
            mock_close.assert_called_once()
