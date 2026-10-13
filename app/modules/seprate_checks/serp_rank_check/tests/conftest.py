"""Shared fixtures for the SERP rank check tests.

Uses the project's isolated-Postgres-schema test helper so
the partial unique index and FK constraints are exercised
against a real database. The DataForSEO provider is mocked
at the service boundary (``_get_serp_client``) and Celery's
``send_task`` is captured so no broker is required.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.shared.tasks.celery_app import celery_app
from app.tests.database import (
    create_isolated_test_engine,
    dispose_isolated_test_engine,
)

from app.modules.seprate_checks.serp_rank_check.model import (
    SerpLanguage,
    SerpLocation,
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
    fake_user = SimpleNamespace(id=FAKE_USER_ID)
    # Yield a fresh session per request (as production
    # does) so concurrent requests never share one
    # SQLAlchemy session.
    factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seed_reference(db_session):
    """Seed the serp_locations / serp_languages reference tables."""
    db_session.add_all(
        [
            SerpLocation(
                location_code=2840,
                name="United States",
                country_iso="US",
                location_type="Country",
            ),
            SerpLocation(
                location_code=2841,
                name="Canada",
                country_iso="CA",
                location_type="Country",
            ),
            SerpLanguage(language_code="en", name="English"),
            SerpLanguage(language_code="fr", name="French"),
        ]
    )
    await db_session.commit()
    return db_session


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
                        "location_code": 2840,
                        "language_code": "en",
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
    """In-memory stand-in for DataForSEOClient."""

    def __init__(self, body=None, cost=0.0005, exc=None):
        self.calls: list[dict] = []
        self._body = body
        self._cost = cost
        self._exc = exc

    def set_response(self, body=None, cost=0.0005, exc=None):
        self._body = body
        self._cost = cost
        self._exc = exc

    async def serp_google_organic_live(
        self, keyword, location_code, language_code, device, depth
    ):
        self.calls.append(
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "device": device,
                "depth": depth,
            }
        )
        if self._exc is not None:
            raise self._exc
        if self._body is not None:
            return self._body
        return make_serp_body([], cost=self._cost)

    async def serp_google_locations(self):
        return make_locations_body()

    async def serp_google_languages(self):
        return make_languages_body()


def make_locations_body():
    return {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "location_code": 2840,
                        "location_name": "United States",
                        "country_iso_code": "US",
                        "location_type": "Country",
                    },
                    {
                        "location_code": 2841,
                        "location_name": "Canada",
                        "country_iso_code": "CA",
                        "location_type": "Country",
                    },
                ],
            }
        ],
    }


def make_languages_body():
    return {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {"language_code": "en", "language_name": "English"},
                    {"language_code": "fr", "language_name": "French"},
                ],
            }
        ],
    }


@pytest_asyncio.fixture
async def fake_serp_client(monkeypatch):
    """Patch the service's provider client factory with a fake."""
    client = FakeSerpClient()

    async def _get():
        return client

    monkeypatch.setattr(
        "app.modules.seprate_checks.serp_rank_check.service._get_serp_client",
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
