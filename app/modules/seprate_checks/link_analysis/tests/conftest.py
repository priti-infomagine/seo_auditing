"""Test fixtures for the link_analysis module."""
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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
