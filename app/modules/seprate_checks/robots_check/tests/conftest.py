"""
Test fixtures for robots_check module tests.
"""
import os
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    path = FIXTURES_DIR / name
    if not path.exists():
        return ""
    return path.read_text()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncSession:
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        try:
            await session.rollback()
        except Exception:
            pass
        try:
            await session.close()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def _override_db(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_http_200_ok():
    """Return a mock httpx client that returns 200 with clean robots.txt."""
    body = load_fixture("clean_robots.txt")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text=body,
            headers={"Content-Type": "text/plain"},
        )
    )
    return httpx.AsyncClient(transport=transport, base_url="https://example.com")


@pytest.fixture
def mock_http_404():
    """Return a mock httpx client that returns 404."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(404, text="Not Found")
    )
    return httpx.AsyncClient(transport=transport, base_url="https://example.com")


@pytest.fixture
def mock_http_unreachable():
    """Return a mock httpx client that raises a connection error."""
    def handler(request):
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, base_url="https://example.com")


@pytest.fixture
def mock_http_https_then_http():
    """HTTPS fails with conn error, HTTP succeeds."""
    body = load_fixture("clean_robots.txt")

    def handler(request):
        if "https" in request.url.scheme:
            raise httpx.ConnectError("Connection refused on HTTPS")
        return httpx.Response(200, text=body, headers={"Content-Type": "text/plain"})

    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)
