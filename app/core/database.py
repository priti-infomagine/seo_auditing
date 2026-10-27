from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import DateTime, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import settings


class TimestampMixin:
    """Adds created_at and updated_at timestamp columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ── Async Engine ─────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=20,
    # Recycle connections after 30 min.  This is a defence-in-depth measure
    # alongside the run_async() fix that ensures the SQLAlchemy async engine's
    # connection pool is accessed from a single event loop (_worker_loop).
    # pool_recycle prevents long-lived connections from going stale (e.g.
    # TCP timeouts, server restarts) which can surface as the same class of
    # "Future attached to a different loop" errors if a recycled connection
    # somehow retains state from a previous loop.
    pool_recycle=1800,
)

# ── Session Factory ──────────────────────────────────────────────────
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Dependency ───────────────────────────────────────────────────────
async def get_db() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Base ─────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass



# ── Lifecycle helpers ────────────────────────────────────────────────
async def init_db() -> None:
    """Create all tables (useful for development / testing)."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT pg_advisory_xact_lock(7419836246283155)"))
            await conn.run_sync(Base.metadata.create_all)

    except Exception as exc:
        from app.core.logger import logger
        logger.error(f"init_db failed: {exc}", exc_info=True)
        raise



async def close_db() -> None:
    """Dispose the engine gracefully."""
    try:
        await engine.dispose()
    except Exception as exc:
        from app.core.logger import logger
        logger.error(f"close_db failed: {exc}", exc_info=True)
        raise
