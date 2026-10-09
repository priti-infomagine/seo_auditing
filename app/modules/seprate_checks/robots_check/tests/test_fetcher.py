"""
Tests for the robots.txt fetcher.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

import httpx

from app.modules.seprate_checks.robots_check import fetcher as fetcher_module
from app.modules.seprate_checks.robots_check.fetcher import (
    FetchStatus,
    fetch_robots_txt,
)
from app.modules.seprate_checks.robots_check.tests.conftest import load_fixture


class MockHTTPClient:
    """Mock HTTPClient that returns a configurable response per call."""

    _mock_response = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
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


def _mock_response(text: str = "", status_code: int = 200, url: str = "https://example.com/robots.txt"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.content = text.encode() if text else b""
    resp.url = MagicMock()
    resp.url.__str__ = lambda self: url
    resp.headers = {}
    return resp


@pytest.mark.asyncio
async def test_fetcher_success():
    """HTTPS 200 → FetchStatus.SUCCESS."""
    body = load_fixture("clean_robots.txt")
    MockHTTPClient._mock_response = _mock_response(body, 200)

    result = await fetch_robots_txt("example.com")

    assert result.fetch_status == FetchStatus.SUCCESS
    assert result.success is True
    assert result.status_code == 200
    assert result.text == body


@pytest.mark.asyncio
async def test_fetcher_404():
    """HTTPS 404 → FetchStatus.NOT_FOUND."""
    MockHTTPClient._mock_response = _mock_response("", 404)

    result = await fetch_robots_txt("example.com")

    assert result.fetch_status == FetchStatus.NOT_FOUND
    assert result.success is False
    assert result.status_code == 404


@pytest.mark.asyncio
async def test_fetcher_unreachable():
    """Connection error → FetchStatus.UNREACHABLE."""

    def raise_conn_error(url):
        raise httpx.ConnectError("Connection refused")

    MockHTTPClient._mock_response = None
    mock_client = MockHTTPClient()
    mock_client.get = AsyncMock(side_effect=raise_conn_error)

    original = fetcher_module.HTTPClient
    fetcher_module.HTTPClient = lambda **kw: mock_client
    try:
        result = await fetch_robots_txt("example.com", max_retries=1)
    finally:
        fetcher_module.HTTPClient = original

    assert result.fetch_status == FetchStatus.UNREACHABLE
    assert result.success is False
    assert result.error is not None


@pytest.mark.asyncio
async def test_fetcher_https_fallback_to_http_success():
    """HTTPS fails with connection error → HTTP fallback succeeds."""

    body = load_fixture("clean_robots.txt")

    class FallbackMockClient:
        call_count = 0

        def __init__(self, **kwargs):
            self.get = AsyncMock(side_effect=self._get)

        async def _get(self, url):
            FallbackMockClient.call_count += 1
            if "https" in str(url):
                raise httpx.ConnectError("Connection refused on HTTPS")
            return _mock_response(body, 200, "http://example.com/robots.txt")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    original = fetcher_module.HTTPClient
    fetcher_module.HTTPClient = FallbackMockClient
    try:
        result = await fetch_robots_txt("example.com", max_retries=1)
    finally:
        fetcher_module.HTTPClient = original

    assert result.fetch_status == FetchStatus.SUCCESS
    assert result.success is True


@pytest.mark.asyncio
async def test_fetcher_content_length():
    """FetchResult should record the content length."""
    body = load_fixture("clean_robots.txt")
    MockHTTPClient._mock_response = _mock_response(body, 200)

    result = await fetch_robots_txt("example.com")

    assert result.content_length == len(body.encode())


@pytest.mark.asyncio
async def test_fetcher_not_found_via_404():
    """FetchStatus.NOT_FOUND when the server returns 404."""
    MockHTTPClient._mock_response = _mock_response("Not found", 404)

    result = await fetch_robots_txt("no-robots.com")

    assert result.fetch_status == FetchStatus.NOT_FOUND
    assert result.success is False
