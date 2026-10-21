"""Test fixtures for the link_analysis module."""
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from app.core.database import get_db
from app.main import app
from app.tests.database import create_isolated_test_engine, dispose_isolated_test_engine


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
        app.dependency_overrides[get_db] = lambda: session
        yield session
        app.dependency_overrides.pop(get_db, None)
        try:
            await session.rollback()
        except Exception:
            pass


@pytest.fixture
def mock_redis():
    """Mock Redis client that stores data in-memory."""
    store: dict = {}

    class _MockRedis:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value, ex=None):
            store[key] = value
            return True

        async def delete(self, key):
            store.pop(key, None)
            return 1

        async def close(self):
            pass

        async def flushdb(self):
            store.clear()

    return _MockRedis()
