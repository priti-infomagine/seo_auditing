"""
Tests for the robots.txt check service.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx

from app.modules.seprate_checks.robots_check import fetcher as fetcher_module
from app.modules.seprate_checks.robots_check.fetcher import FetchStatus
from app.modules.seprate_checks.robots_check.model import (
    OverallStatus,
    RobotCheck,
    Severity,
)
from app.modules.seprate_checks.robots_check.service import RobotsCheckService
from app.modules.seprate_checks.robots_check.tests.conftest import load_fixture


class MockHTTPClient:
    """Mock HTTPClient that returns a class-level mock response."""

    _mock_response = None

    def __init__(self, **kwargs):
        self.get = AsyncMock(return_value=MockHTTPClient._mock_response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockSitemapClient:
    """Mock httpx.AsyncClient for sitemap HEAD requests."""

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


@pytest.fixture(autouse=True)
def patch_clients():
    """Patch HTTPClient in fetcher and AsyncClient in service."""
    import app.modules.seprate_checks.robots_check.service as svc_module

    orig_http_client = fetcher_module.HTTPClient
    orig_async_client = svc_module.httpx.AsyncClient
    orig_head = svc_module.httpx.AsyncClient

    fetcher_module.HTTPClient = MockHTTPClient
    svc_module.httpx.AsyncClient = MockSitemapClient
    MockHTTPClient._mock_response = None
    MockSitemapClient._head_response = None

    yield MockHTTPClient, MockSitemapClient

    fetcher_module.HTTPClient = orig_http_client
    svc_module.httpx.AsyncClient = orig_async_client


@pytest.mark.asyncio
async def test_service_cache_hit(db_session):
    """Cached fresh row → no HTTP fetch."""
    from datetime import timedelta
    body = load_fixture("clean_robots.txt")
    recent = datetime.now(timezone.utc) - timedelta(hours=1)

    existing = RobotCheck(
        domain="example.com",
        exists=True,
        status_code=200,
        fetch_status=FetchStatus.SUCCESS,
        size_bytes=len(body),
        raw_content=body,
        fetched_url="https://example.com/robots.txt",
        user_agent_groups=[],
        sitemaps_declared=["https://example.com/sitemap.xml"],
        sitemap_reachability=[],
        syntax_warnings=[],
        blocks_entire_site=False,
        blocks_assets=False,
        oversized=False,
        overall_status=OverallStatus.PASS,
        severity=Severity.NONE,
        evidence=None,
        why=None,
        recommendation=None,
        check_version="1.0.0",
    )
    existing.created_at = recent
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    service = RobotsCheckService(db_session)
    result = await service.run_check("example.com", force=False)

    assert result.exists is True
    assert result.fetch_status == FetchStatus.SUCCESS
    assert result.domain == "example.com"


@pytest.mark.asyncio
async def test_service_cache_miss_and_store(db_session):
    """No cache → fresh fetch + new row stored."""
    body = load_fixture("clean_robots.txt")
    mock_resp = MagicMock()
    mock_resp.get = AsyncMock(return_value=_make_response(body, 200))

    MockHTTPClient._mock_response = _make_response(body, 200)
    MockSitemapClient._head_response = _make_response("", 200)

    service = RobotsCheckService(db_session)
    result = await service.run_check("example.com", force=True)

    assert result.fetch_status == FetchStatus.SUCCESS
    assert result.exists is True
    assert result.domain == "example.com"
    assert result.sitemaps_declared == ["https://example.com/sitemap.xml"]


@pytest.mark.asyncio
async def test_service_parse_error_degrades_gracefully(db_session):
    """Malformed robots.txt → still stores row with syntax_warning."""
    raw = "garbage line no colon\nalso garbage\nNo colons here"
    MockHTTPClient._mock_response = _make_response(raw, 200)
    MockSitemapClient._head_response = None

    service = RobotsCheckService(db_session)
    result = await service.run_check("example.com", force=True)

    assert result.fetch_status == FetchStatus.SUCCESS
    assert result.syntax_warnings is not None


@pytest.mark.asyncio
async def test_service_returns_cached_from_db(db_session):
    """get_latest returns stored result without HTTP."""
    existing = RobotCheck(
        domain="cached-test.com",
        exists=True,
        status_code=200,
        fetch_status=FetchStatus.SUCCESS,
        size_bytes=100,
        blocks_entire_site=False,
        blocks_assets=False,
        oversized=False,
        overall_status=OverallStatus.PASS,
        severity=Severity.NONE,
        check_version="1.0.0",
    )
    db_session.add(existing)
    await db_session.commit()

    service = RobotsCheckService(db_session)
    result = await service.get_latest("cached-test.com")

    assert result is not None
    assert result.domain == "cached-test.com"
    assert result.fetch_status == FetchStatus.SUCCESS


@pytest.mark.asyncio
async def test_service_get_latest_not_found(db_session):
    """get_latest returns None for unknown domain."""
    service = RobotsCheckService(db_session)
    result = await service.get_latest("nonexistent-domain-12345.com")

    assert result is None


@pytest.mark.asyncio
async def test_service_www_normalization(db_session):
    """www.example.com → normalized to example.com."""
    body = load_fixture("clean_robots.txt")
    MockHTTPClient._mock_response = _make_response(body, 200)
    MockSitemapClient._head_response = _make_response("", 200)

    service = RobotsCheckService(db_session)
    result = await service.run_check("www.example.com", force=True)

    assert result.domain == "example.com"
