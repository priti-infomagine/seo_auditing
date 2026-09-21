"""
Shared API dependencies.

Common FastAPI dependencies used across endpoint routers.
"""
from typing import AsyncGenerator, Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logger import logger
from app.core.security import get_current_user
from app.modules.auth.models.users import User


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for API routes."""
    try:
        async for session in get_db():
            yield session
    except Exception as exc:
        logger.error(f"get_db_session: database session error: {exc}", exc_info=True)
        raise


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Optional auth dependency.

    Returns None only when no token is supplied. Lets 401 propagate
    from get_current_user on bad/expired tokens so auth failures
    are never silently downgraded to anonymous access.
    """
    if credentials is None:
        return None
    return await get_current_user(credentials=credentials, db=db)


__all__ = ["get_db_session", "get_current_user_optional"]
