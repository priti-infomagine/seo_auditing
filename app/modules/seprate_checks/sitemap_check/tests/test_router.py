"""
Tests for the sitemap check router (HTTP API).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.main import app
from app.modules.seprate_checks.robots_check import fetcher as robots_fetcher_module
from app.modules.seprate_checks.sitemap_check import fetcher as sitemap_fetcher_module
from app.modules.seprate_checks.sitemap_check.model import (
    FetchStatus,
    OverallStatus,
    Severity,
    SitemapCheck,
)
from app.modules.seprate_checks.sitemap_check.tests.conftest import load_fixture


class MockHTTPClient:
    """Mock HTTPClient that returns different responses based on URL."""

    _robots_response = None
    _sitemap_responses: dict = {}

    def __init__(self, **kwargs):
        self.get = AsyncMock(side_effect=self._get)

    async def _get(self, url):
        url_str = str(url)

        if "robots.txt" in url_str:
            return MockHTTPClient._robots_response or _default_robots()

        for path, response in MockHTTPClient._sitemap_responses.items():
            if path in url_str:
                return response

        return _default_404(url_str)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _resp(text=b"", status_code=200, url="https://example.com/sitemap.xml", content_type="application/xml"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text.decode() if isinstance(text, bytes) else text
    resp.content = text if isinstance(text, bytes) else text.encode()
    resp.url = MagicMock()
    resp.url.__str__ = lambda self: url
    resp.headers = {"content-type": content_type} if content_type else {}
    return resp


def _default_robots():
    return _resp(
        b"User-agent: *\nDisallow: /private/\nSitemap: https://example.com/sitemap.xml\n",
        200,
        "https://example.com/robots.txt",
        "text/plain",
    )


def _default_404(url):
    return _resp(b"Not Found", 404, url, "text/plain")


def _sitemap_xml(entries=3):
    urls = "".join(
        f"<url><loc>https://example.com/page/{i}</loc></url>"
        for i in range(1, entries + 1)
    )
    return f"<?xml version='1.0'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>{urls}</urlset>".encode()


@pytest.fixture
def patch_clients(db_session):
    orig_robots = robots_fetcher_module.HTTPClient
    orig_sitemap = sitemap_fetcher_module.HTTPClient

    robots_fetcher_module.HTTPClient = MockHTTPClient
    sitemap_fetcher_module.HTTPClient = MockHTTPClient
    MockHTTPClient._robots_response = None
    MockHTTPClient._sitemap_responses = {}

    async def _get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db

    yield MockHTTPClient

    robots_fetcher_module.HTTPClient = orig_robots
    sitemap_fetcher_module.HTTPClient = orig_sitemap
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_router_check_success(db_session, patch_clients):
    """POST /check → 200, returns sitemap results with four columns."""
    body = load_fixture("robots_with_sitemap.txt")
    MockHTTPClient._robots_response = _resp(body, 200, "https://example.com/robots.txt", "text/plain")
    MockHTTPClient._sitemap_responses = {"/sitemap.xml": _resp(_sitemap_xml(5), 200)}

    async with ASGITransport(app=app) as transport:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/sitemap/check",
                json={"url": "example.com"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["domain"] == "example.com"
    assert data["robots_fetch_status"] == "success"
    assert "https://example.com/sitemap.xml" in data["sitemaps_declared"]
    assert len(data["sitemap_results"]) > 0
    sr = data["sitemap_results"][0]
    # Four columns
    assert sr["final_url"]
    assert sr["status_code"] == 200
    assert sr["content_type"]
    assert isinstance(sr["entry_count"], int)


@pytest.mark.asyncio
async def test_router_check_invalid_url(db_session, patch_clients):
    """POST /check with empty url → 422."""
    patch_clients

    async with ASGITransport(app=app) as transport:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/sitemap/check",
                json={"url": ""},
            )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_router_check_www_normalized(db_session, patch_clients):
    """POST /check with www.example.com → domain == example.com."""
    body = load_fixture("robots_with_sitemap.txt")
    MockHTTPClient._robots_response = _resp(body, 200, "https://example.com/robots.txt", "text/plain")
    MockHTTPClient._sitemap_responses = {"/sitemap.xml": _resp(_sitemap_xml(3), 200)}

    async with ASGITransport(app=app) as transport:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/sitemap/check",
                json={"url": "www.example.com"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["domain"] == "example.com"


@pytest.mark.asyncio
async def test_router_result_not_found(db_session, patch_clients):
    """GET /result/unknown-domain.com → 404."""
    patch_clients

    async with ASGITransport(app=app) as transport:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/sitemap/result/some-unknown-domain-12345.com")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_router_result_returns_cached(db_session, patch_clients):
    """GET after check → 200 with cached data."""
    patch_clients
    body = load_fixture("robots_with_sitemap.txt")
    existing = SitemapCheck(
        domain="cached-test.com",
        robots_fetch_status=FetchStatus.SUCCESS,
        robots_status_code=200,
        robots_final_url="https://cached-test.com/robots.txt",
        raw_robots_content=body,
        sitemaps_declared=["https://cached-test.com/sitemap.xml"],
        sitemap_results=[
            {
                "url": "https://cached-test.com/sitemap.xml",
                "final_url": "https://cached-test.com/sitemap.xml",
                "status_code": 200,
                "content_type": "application/xml",
                "entry_count": 42,
                "is_index": False,
                "redirected": False,
                "error": None,
            }
        ],
        findings=[
            {
                "code": "sitemap_ok",
                "severity": "none",
                "status": "pass",
                "message": "All sitemaps reachable.",
                "evidence": "1 sitemap file(s) verified",
            }
        ],
        overall_status=OverallStatus.PASS,
        severity=Severity.NONE,
        check_version="1.0.0",
    )
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    async with ASGITransport(app=app) as transport:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/sitemap/result/cached-test.com")

    assert response.status_code == 200
    data = response.json()
    assert data["domain"] == "cached-test.com"
    assert data["overall_status"] == "pass"
    assert data["sitemap_count"] == 1
    assert data["sitemap_results"][0]["entry_count"] == 42
    assert "### Discovered sitemaps" in data["report_markdown"]
