"""
Test fixtures for the sitemap_check module.
"""
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.tests.database import create_isolated_test_engine, dispose_isolated_test_engine

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    path = FIXTURES_DIR / name
    if not path.exists():
        return ""
    return path.read_text()


def load_fixture_bytes(name: str) -> bytes:
    path = FIXTURES_DIR / name
    if not path.exists():
        return b""
    return path.read_bytes()


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
