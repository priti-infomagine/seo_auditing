"""
Shared API dependencies.

Common FastAPI dependencies used across endpoint routers.
"""
from typing import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for API routes."""
    try:
        async for session in get_db():
            yield session
    except Exception as exc:
        logger.error(f"get_db_session: database session error: {exc}", exc_info=True)
        raise


__all__ = ["get_db_session"]
