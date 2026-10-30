"""Shared fixtures for the SERP rank check tests.

Uses the project's isolated-Postgres-schema test helper so
the partial unique index and constraints are exercised against
a real database. The DataForSEO provider is mocked at the service
boundary (``get_serp_client``).
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_db
from app.main import app
from app.modules.separate_checks.serp_rank_check.exceptions import (
    SerpProvider4xx,
    SerpProvider5xx,
    SerpProviderTimeout,
)
from app.tests.database import (
    create_isolated_test_engine,
    dispose_isolated_test_engine,
)

FAKE_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    engine, schema = await create_isolated_test_engine()
    yield engine
    await dispose_isolated_test_engine(engine, schema)


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncSession:
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture(autouse=True)
def override_dependencies(db_engine, db_session):
    factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.clear()


# ── Fake DataForSEO provider ─────────────────────────────
def organic_item(position, url, title="Result Title", snippet="Result snippet"):
    return {
        "type": "organic",
        "rank_group": position,
        "rank_absolute": position,
        "domain": url,
        "url": url,
        "title": title,
        "description": snippet,
        "snippet": snippet,
    }


def feature_item(feature_type, **extra):
    item = {"type": feature_type}
    item.update(extra)
    return item


def make_serp_body(items, cost=0.0005):
    return {
        "status_code": 20000,
        "status_message": "Ok.",
        "time": "0.10 sec.",
        "cost": cost,
        "tasks_count": 1,
        "tasks_error": 0,
        "tasks": [
            {
                "status_code": 20000,
                "status_message": "Ok.",
                "time": "0.10 sec.",
                "cost": cost,
                "result_count": len(items),
                "path": ["v3", "serp", "google", "organic", "live", "advanced"],
                "data": {},
                "result": [
                    {
                        "keyword": "test keyword",
                        "location_name": "United States",
                        "language_name": "English",
                        "device": "desktop",
                        "depth": 10,
                        "items_count": len(items),
                        "items": items,
                    }
                ],
            }
        ],
    }


def make_serp_body_with_target_at(
    target_position: int,
    target_url: str = "https://example.com/",
    total: int = 10,
    cost: float = 0.0005,
):
    """Build a SERP body with *total* organic items.

    The item at *target_position* uses *target_url*; all others get
    a generic ``other-{i}.com`` URL.  Positions are 1-indexed.
    """
    items = []
    for pos in range(1, total + 1):
        if pos == target_position:
            url = target_url
        else:
            url = f"https://other-{pos}.com/"
        items.append(organic_item(pos, url))
    return make_serp_body(items, cost=cost)


def make_serp_body_no_match(
    total: int = 10, cost: float = 0.0005
):
    """Build a SERP body with *total* organic items, none matching."""
    items = [organic_item(i, f"https://other-{i}.com/") for i in range(1, total + 1)]
    return make_serp_body(items, cost=cost)


def make_location(code, name, location_type="City", country_iso="IN"):
    return {
        "location_code": code,
        "location_name": name,
        "location_code_parent": None,
        "country_iso_code": country_iso,
        "location_type": location_type,
    }


def make_locations_body(items):
    """Build a DataForSEO ``/serp/google/locations`` response body."""
    return {
        "status_code": 20000,
        "status_message": "Ok.",
        "cost": 0,
        "tasks_count": 1,
        "tasks_error": 0,
        "tasks": [
            {
                "status_code": 20000,
                "status_message": "Ok.",
                "result_count": len(items),
                "path": ["v3", "serp", "google", "locations"],
                "result": items,
            }
        ],
    }


class FakeSerpClient:
    """In-memory stand-in for SERPDataForSEOClient."""

    def __init__(
        self,
        body=None,
        cost=0.0005,
        exc=None,
        delay=0,
        locations_body=None,
    ):
        self.calls: list[dict] = []
        self.location_calls: list[dict] = []
        self._body = body
        self._cost = cost
        self._exc = exc
        self._delay = delay
        self._locations_body = locations_body

    def set_response(self, body=None, cost=0.0005, exc=None, delay=0):
        self._body = body
        self._cost = cost
        self._exc = exc
        self._delay = delay

    def set_locations_response(self, body):
        """Set the raw body returned by ``serp_google_locations``."""
        self._locations_body = body

    async def serp_google_organic_live_advanced(
        self,
        *,
        keyword,
        location_name=None,
        location_code=None,
        language_name,
        device,
        depth,
        find_targets_in=None,
        stop_crawl_on_match=None,
        target_search_mode=None,
    ):
        self.calls.append(
            {
                "keyword": keyword,
                "location_name": location_name,
                "location_code": location_code,
                "language_name": language_name,
                "device": device,
                "depth": depth,
                "find_targets_in": find_targets_in,
                "stop_crawl_on_match": stop_crawl_on_match,
                "target_search_mode": target_search_mode,
            }
        )
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._exc is not None:
            # Convert raw httpx errors to typed provider exceptions
            # so the service's try/except can classify them.
            import httpx as _httpx

            if isinstance(self._exc, _httpx.TimeoutException):
                raise SerpProviderTimeout(str(self._exc)) from self._exc
            if isinstance(self._exc, _httpx.HTTPStatusError):
                code = self._exc.response.status_code if self._exc.response else 0
                if 500 <= code < 600:
                    raise SerpProvider5xx(str(self._exc)) from self._exc
                raise SerpProvider4xx(str(self._exc)) from self._exc
            raise self._exc
        if self._body is not None:
            return self._body
        return make_serp_body([], cost=self._cost)

    async def serp_google_locations(
        self, *, country=None, **_kwargs
    ):
        """Return a canned DataForSEO locations response body."""
        self.location_calls.append({"country": country})
        if self._locations_body is not None:
            return self._locations_body
        return {
            "status_code": 20000,
            "status_message": "Ok.",
            "cost": 0,
            "tasks_count": 1,
            "tasks": [
                {
                    "status_code": 20000,
                    "result_count": 0,
                    "result": [],
                }
            ],
        }

    async def aclose(self) -> None:
        pass


@pytest.fixture(autouse=True)
def clear_locations_cache():
    """Reset the module-level locations cache before each test so
    cache hits don't leak between tests."""
    from app.modules.separate_checks.serp_rank_check import router as _router

    _router._locations_cache.clear()
    yield
    _router._locations_cache.clear()


@pytest.fixture(autouse=True)
def mock_domain_preview(monkeypatch):
    """Prevent real HTTP calls during tests by stubbing ``fetch_domain_preview``.

    Returns a realistic preview dict so tests can assert on
    ``domain_preview`` values if needed.  Individual tests can
    override this by re-patching
    ``app.modules.separate_checks.serp_rank_check.service.fetch_domain_preview``.
    """
    async def _mock_preview(domain: str) -> dict:
        return {
            "site_name": "Test Site",
            "domain": domain,
            "favicon": f"https://{domain}/favicon.ico",
            "title": "Test Page Title",
            "description": "Test page description.",
            "warning": None,
        }

    monkeypatch.setattr(
        "app.modules.separate_checks.serp_rank_check.service.fetch_domain_preview",
        _mock_preview,
    )


@pytest_asyncio.fixture
async def fake_serp_client(monkeypatch):
    """Patch the provider client factory with a fake.

    Patches both the service-layer and router-layer references so the
    ``/locations`` endpoint (which calls ``get_serp_client`` directly)
    uses the same in-memory fake as the rank-check path.
    """
    client = FakeSerpClient()

    async def _get():
        return client

    monkeypatch.setattr(
        "app.modules.separate_checks.serp_rank_check.service.get_serp_client",
        _get,
    )
    monkeypatch.setattr(
        "app.modules.separate_checks.serp_rank_check.router.get_serp_client",
        _get,
    )
    return client


@pytest_asyncio.fixture
async def service_session_factory(db_engine, monkeypatch):
    """Redirect the service's task-facing sessions to the test schema."""
    factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(
        "app.modules.separate_checks.serp_rank_check.service.async_session_factory",
        factory,
    )
    return factory
