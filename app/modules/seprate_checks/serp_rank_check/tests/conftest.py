"""Shared fixtures for the SERP rank check tests.

Uses the project's isolated-Postgres-schema test helper so
the partial unique index and constraints are exercised against
a real database. The DataForSEO provider is mocked at the service
boundary (``get_serp_client``) and Celery's ``send_task`` is
captured so no broker is required.
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_db
from app.main import app
from app.modules.seprate_checks.serp_rank_check.exceptions import (
    SerpProvider4xx,
    SerpProvider5xx,
    SerpProviderTimeout,
)
from app.shared.tasks.celery_app import celery_app
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


@pytest.fixture
def sent_tasks(monkeypatch):
    """Capture Celery send_task calls instead of hitting a broker."""
    sent: list[dict] = []

    def fake_send_task(name, args=None, queue=None, **kwargs):
        sent.append({"name": name, "args": args, "queue": queue})
        return SimpleNamespace(id=f"task-{uuid.uuid4()}")

    monkeypatch.setattr(celery_app, "send_task", fake_send_task)
    return sent


# ── Fake DataForSEO provider ─────────────────────────────
def organic_item(position, url, title="Result Title", snippet="Result snippet"):
    return {
        "type": "organic",
        "rank_group": position,
        "rank_absolute": position,
        "domain": url,
        "url": url,
        "title": title,
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


class FakeSerpClient:
    """In-memory stand-in for SERPDataForSEOClient."""

    def __init__(self, body=None, cost=0.0005, exc=None, delay=0):
        self.calls: list[dict] = []
        self._body = body
        self._cost = cost
        self._exc = exc
        self._delay = delay

    def set_response(self, body=None, cost=0.0005, exc=None, delay=0):
        self._body = body
        self._cost = cost
        self._exc = exc
        self._delay = delay

    async def serp_google_organic_live_advanced(
        self, *, keyword, location_name, language_name, device, depth
    ):
        self.calls.append(
            {
                "keyword": keyword,
                "location_name": location_name,
                "language_name": language_name,
                "device": device,
                "depth": depth,
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

    async def aclose(self) -> None:
        pass


@pytest_asyncio.fixture
async def fake_serp_client(monkeypatch):
    """Patch the service's provider client factory with a fake."""
    client = FakeSerpClient()

    async def _get():
        return client

    monkeypatch.setattr(
        "app.modules.seprate_checks.serp_rank_check.service.get_serp_client",
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
        "app.modules.seprate_checks.serp_rank_check.service.async_session_factory",
        factory,
    )
    return factory


@pytest.fixture
def preview_artifacts(monkeypatch):
    """Mock the preview artifact writer used by build_preview."""
    state = {
        "urls": {
            "html_url": "/api/v1/serp/previews/x/preview.html",
            "image_url": "/api/v1/serp/previews/x/screenshot.png",
        },
        "raise": None,
    }

    async def fake_save(check_id, html_content, device):
        if state["raise"] is not None:
            raise state["raise"]
        return state["urls"]

    monkeypatch.setattr(
        "app.modules.seprate_checks.serp_rank_check.service.save_preview_artifacts",
        fake_save,
    )
    return state
