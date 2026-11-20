import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.fetchers.http_fetcher import HttpFetcher


def _stream_context(response):
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=None)
    return context


def _response(url):
    response = MagicMock()
    response.status_code = 200
    response.url = url
    response.headers = {"content-type": "text/html"}
    response.history = []
    response.http_version = "HTTP/1.1"
    return response


@pytest.mark.asyncio
async def test_fetch_stops_when_response_exceeds_size_limit():
    url = "https://example.com/"
    response = _response(url)
    finished = False

    async def chunks():
        nonlocal finished
        yield b"123"
        yield b"45"
        finished = True

    response.aiter_bytes = chunks
    fetcher = HttpFetcher(config=CrawlConfig(max_response_size=4))
    with patch(
        "app.modules.crawler.fetchers.http_fetcher.validate_url_ssrf_async",
        new_callable=AsyncMock,
    ), patch.object(
        fetcher._client, "stream", return_value=_stream_context(response)
    ):
        try:
            result = await fetcher.fetch(url)
        finally:
            await fetcher.close()

    assert result.error_type == "content_too_large"
    assert result.content == b""
    assert result.content_length == 5
    assert not finished


@pytest.mark.asyncio
async def test_fetch_stops_a_slow_stream_at_total_timeout():
    url = "https://example.com/"
    response = _response(url)

    async def chunks():
        yield b"partial"
        await asyncio.Event().wait()

    response.aiter_bytes = chunks
    fetcher = HttpFetcher(config=CrawlConfig(request_timeout=0.02))
    with patch(
        "app.modules.crawler.fetchers.http_fetcher.validate_url_ssrf_async",
        new_callable=AsyncMock,
    ), patch.object(
        fetcher._client, "stream", return_value=_stream_context(response)
    ) as mock_stream:
        try:
            result = await fetcher.fetch(url)
        finally:
            await fetcher.close()

    assert result.error_type == "timeout"
    assert "total timeout" in result.error
    mock_stream.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_stops_if_ssrf_dns_validation_hangs():
    async def stalled_validation(*args, **kwargs):
        await asyncio.Event().wait()

    fetcher = HttpFetcher(config=CrawlConfig(request_timeout=0.02))
    with patch(
        "app.modules.crawler.fetchers.http_fetcher.validate_url_ssrf_async",
        new=stalled_validation,
    ), patch.object(fetcher._client, "stream") as mock_stream:
        try:
            result = await fetcher.fetch("https://example.com/")
        finally:
            await fetcher.close()

    assert result.error_type == "timeout"
    assert "URL validation exceeded total timeout" in result.error
    mock_stream.assert_not_called()
