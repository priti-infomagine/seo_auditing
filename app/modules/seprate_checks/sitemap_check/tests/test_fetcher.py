"""
Tests for the sitemap fetcher.
"""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.modules.seprate_checks.sitemap_check import fetcher as fetcher_module
from app.modules.seprate_checks.sitemap_check.fetcher import (
    FetchStatus,
    fetch_sitemap,
)


class MockHTTPClient:
    """Mock HTTPClient that returns a configurable response."""

    _mock_response = None

    def __init__(self, **kwargs):
        self.get = AsyncMock(return_value=MockHTTPClient._mock_response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.fixture(autouse=True)
def patch_http_client():
    original = fetcher_module.HTTPClient
    fetcher_module.HTTPClient = MockHTTPClient
    yield MockHTTPClient
    fetcher_module.HTTPClient = original
    MockHTTPClient._mock_response = None


def _mock_response(content=b"", status_code=200, url="https://example.com/sitemap.xml", content_type="application/xml"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.url = MagicMock()
    resp.url.__str__ = lambda self: url
    resp.headers = {"content-type": content_type} if content_type else {}
    return resp


@pytest.mark.asyncio
async def test_fetch_sitemap_success():
    """200 response → FetchStatus.SUCCESS."""
    xml = b"<?xml version='1.0'?><urlset><url><loc>https://example.com/</loc></url></urlset>"
    MockHTTPClient._mock_response = _mock_response(xml, 200)

    result = await fetch_sitemap("https://example.com/sitemap.xml")

    assert result.fetch_status == FetchStatus.SUCCESS
    assert result.success is True
    assert result.status_code == 200
    assert result.content == xml
    assert result.content_length == len(xml)


@pytest.mark.asyncio
async def test_fetch_sitemap_404():
    """404 → FetchStatus.NOT_FOUND."""
    MockHTTPClient._mock_response = _mock_response(b"Not found", 404)

    result = await fetch_sitemap("https://example.com/sitemap.xml")

    assert result.fetch_status == FetchStatus.NOT_FOUND
    assert result.success is False
    assert result.status_code == 404


@pytest.mark.asyncio
async def test_fetch_sitemap_unreachable():
    """Connection error → FetchStatus.UNREACHABLE."""
    MockHTTPClient._mock_response = None

    class FailingClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    fetcher_module.HTTPClient = FailingClient
    try:
        result = await fetch_sitemap("https://example.com/sitemap.xml", max_retries=1)
    finally:
        fetcher_module.HTTPClient = MockHTTPClient

    assert result.fetch_status == FetchStatus.UNREACHABLE
    assert result.success is False
    assert result.error is not None


@pytest.mark.asyncio
async def test_fetch_sitemap_https_fallback_to_http():
    """HTTPS connection error → HTTP fallback succeeds."""
    xml = b"<?xml version='1.0'?><urlset></urlset>"

    class FallbackMockClient:
        def __init__(self, **kwargs):
            self.get = AsyncMock(side_effect=self._get)

        async def _get(self, url):
            if "https" in str(url):
                raise httpx.ConnectError("Connection refused on HTTPS")
            return _mock_response(xml, 200, "http://example.com/sitemap.xml")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    fetcher_module.HTTPClient = FallbackMockClient
    try:
        result = await fetch_sitemap("https://example.com/sitemap.xml", max_retries=1)
    finally:
        fetcher_module.HTTPClient = MockHTTPClient

    assert result.fetch_status == FetchStatus.SUCCESS
    assert result.success is True
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_fetch_sitemap_content_type_extraction():
    """Content-Type header is extracted and normalized."""
    xml = b"<?xml version='1.0'?><urlset></urlset>"
    MockHTTPClient._mock_response = _mock_response(
        xml, 200, content_type="application/xml"
    )

    result = await fetch_sitemap("https://example.com/sitemap.xml")

    assert result.content_type == "application/xml"


@pytest.mark.asyncio
async def test_fetch_sitemap_final_url_after_redirect():
    """final_url reflects the redirected URL."""
    xml = b"<?xml version='1.0'?><urlset></urlset>"
    response = _mock_response(xml, 200, url="http://example.com/redirected-sitemap.xml")
    MockHTTPClient._mock_response = response

    result = await fetch_sitemap("https://example.com/sitemap.xml")

    assert result.final_url == "http://example.com/redirected-sitemap.xml"
