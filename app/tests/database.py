from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import settings
from app.core.database import Base


async def create_isolated_test_engine() -> tuple[AsyncEngine, str]:
    schema = f"test_{uuid4().hex}"
    admin_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    finally:
        await admin_engine.dispose()

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": schema}},
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    except BaseException:
        await dispose_isolated_test_engine(engine, schema)
        raise

    return engine, schema


async def dispose_isolated_test_engine(
    engine: AsyncEngine,
    schema: str,
) -> None:
    await engine.dispose()
    admin_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    finally:
        await admin_engine.dispose()