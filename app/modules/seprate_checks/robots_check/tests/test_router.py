"""
Tests for the robots check router (HTTP API).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.main import app
from app.modules.seprate_checks.robots_check import fetcher as fetcher_module
from app.modules.seprate_checks.robots_check.model import (
    FetchStatus as _FS,
    OverallStatus,
    RobotCheck,
    Severity,
)
from app.modules.seprate_checks.robots_check.tests.conftest import load_fixture


class MockHTTPClient:
    _mock_response = None

    def __init__(self, **kwargs):
        self.get = AsyncMock(return_value=MockHTTPClient._mock_response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockSitemapClient:
    _head_response = None

    def __init__(self, **kwargs):
        self.head = AsyncMock(return_value=MockSitemapClient._head_response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    @property
    def is_closed(self):
        return False

    async def aclose(self):
        pass


def _make_response(text: str = "", status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.content = text.encode() if text else b""
    resp.url = MagicMock()
    resp.url.__str__ = lambda self: "https://example.com/robots.txt"
    resp.headers = {}
    return resp


@pytest.fixture
def patch_clients(db_session):
    import app.modules.seprate_checks.robots_check.service as svc_module

    orig_http = fetcher_module.HTTPClient
    orig_async = svc_module.httpx.AsyncClient

    fetcher_module.HTTPClient = MockHTTPClient
    svc_module.httpx.AsyncClient = MockSitemapClient
    MockHTTPClient._mock_response = None
    MockSitemapClient._head_response = None

    async def _get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db

    yield MockHTTPClient, MockSitemapClient

    fetcher_module.HTTPClient = orig_http
    svc_module.httpx.AsyncClient = orig_async
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_router_check_success(db_session, patch_clients):
    """POST /check → 200, returns response model."""
    MockHTTPClient, MockSitemapClient = patch_clients
    body = load_fixture("clean_robots.txt")
    MockHTTPClient._mock_response = _make_response(body, 200)
    MockSitemapClient._head_response = _make_response("", 200)

    async with ASGITransport(app=app) as transport:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/v1/robots/check", json={"domain": "example.com"})

    assert response.status_code == 200
    data = response.json()
    assert data["domain"] == "example.com"
    assert data["exists"] is True
    assert data["fetch_status"] == "success"
    assert data["raw_content"] == body
    assert data["findings"]
    assert data["findings"][0]["evidence"]
    assert data["recommendations"]
    assert data["recommendations"][0]["recommendation"]
    assert "### Sitemaps" in data["report_markdown"]
    assert "### Crawler rules" in data["report_markdown"]
    assert "### Raw robots.txt" in data["report_markdown"]
    assert "### Recommendations and fixes" in data["report_markdown"]
    assert "- Disallow: /private/" in data["report_markdown"]
    assert body in data["report_markdown"]


@pytest.mark.asyncio
async def test_router_check_invalid_domain(db_session, patch_clients):
    """POST /check with empty domain → 422 (Pydantic validation)."""
    patch_clients

    async with ASGITransport(app=app) as transport:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/v1/robots/check", json={"domain": ""})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_router_check_with_www(db_session, patch_clients):
    """POST /check with www.example.com → normalized to example.com."""
    MockHTTPClient, MockSitemapClient = patch_clients
    body = load_fixture("clean_robots.txt")
    MockHTTPClient._mock_response = _make_response(body, 200)
    MockSitemapClient._head_response = _make_response("", 200)

    async with ASGITransport(app=app) as transport:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/v1/robots/check", json={"domain": "www.example.com"})

    assert response.status_code == 200
    data = response.json()
    assert data["domain"] == "example.com"


@pytest.mark.asyncio
async def test_router_result_not_found(db_session, patch_clients):
    """GET /result/unknown.com → 404."""
    patch_clients

    async with ASGITransport(app=app) as transport:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/robots/result/some-unknown-domain-12345.com")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_router_result_returns_cached(db_session, patch_clients):
    """GET after check → 200 with cached data."""
    patch_clients
    body = load_fixture("clean_robots.txt")
    existing = RobotCheck(
        domain="cached-test.com",
        exists=True,
        status_code=200,
        fetch_status=_FS.SUCCESS,
        size_bytes=len(body),
        raw_content=body,
        findings=[{
            "code": "robots_ok",
            "severity": "none",
            "status": "pass",
            "message": "robots.txt is well-formed",
            "evidence": "All checks passed",
        }],
        fetched_url="https://cached-test.com/robots.txt",
        user_agent_groups=[],
        sitemaps_declared=["https://cached-test.com/sitemap.xml"],
        sitemap_reachability=[],
        syntax_warnings=[],
        blocks_entire_site=False,
        blocks_assets=False,
        oversized=False,
        overall_status=OverallStatus.PASS,
        severity=Severity.NONE,
        check_version="1.0.0",
    )
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    async with ASGITransport(app=app) as transport:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/robots/result/cached-test.com")

    assert response.status_code == 200
    data = response.json()
    assert data["domain"] == "cached-test.com"
    assert data["fetch_status"] == "success"
    assert data["raw_content"] == body
    assert data["findings"][0]["evidence"] == "All checks passed"
    assert data["recommendations"][0]["recommendation"]


@pytest.mark.asyncio
async def test_router_check_404_result(db_session, patch_clients):
    """POST /check with a domain returning 404 → NOT_FOUND status."""
    MockHTTPClient, MockSitemapClient = patch_clients
    MockHTTPClient._mock_response = _make_response("Not found", 404)

    async with ASGITransport(app=app) as transport:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/v1/robots/check", json={"domain": "example.com"})

    assert response.status_code == 200
    data = response.json()
    assert data["fetch_status"] == "not_found"
    assert data["exists"] is False
