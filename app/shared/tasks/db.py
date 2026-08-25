import asyncio
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import async_session_factory, engine


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def run_async(coro):
    """
    Run *coro* in a fresh event loop (via ``asyncio.run``).

    The SQLAlchemy ``AsyncEngine`` and its connection pool are module-level
    singletons.  Each ``asyncio.run`` call creates *and destroys* a new event
    loop, but pooled asyncpg connections created under one loop would survive
    into the next ``asyncio.run`` invocation.  When the pool subsequently tries
    to validate (``pool_pre_ping``) or terminate those stale connections,
    asyncpg calls ``self._loop.create_task()`` on the **old, closed** loop and
    raises ``RuntimeError: Event loop is closed``.

    To prevent this we dispose the engine — gracefully closing every pooled
    connection — **before** the loop is torn down, while the current event
    loop is still alive.
    """
    async def _wrapper():
        try:
            return await coro
        finally:
            # Close all pooled connections on the still-alive loop so they
            # are never touched by a subsequent — different — loop.
            try:
                await engine.dispose()
            except Exception:
                pass  # best-effort; non-fatal during shutdown

    return asyncio.run(_wrapper())
