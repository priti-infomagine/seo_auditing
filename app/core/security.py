"""
Security utilities.

- Password hashing / verification (bcrypt via passlib)
- Token hashing for storing refresh tokens securely
- JWT-based authentication: get current user from access token
"""
import hashlib
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.utils import decode_token
from app.modules.auth.models.token_blacklist import TokenBlacklist
from app.modules.auth.models.users import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its hashed version."""
    return pwd_context.verify(plain_password, hashed_password)


def hash_token(token: str) -> str:
    """
    Hash a JWT token using SHA-256 for secure storage.

    We store the hash of refresh tokens in the database so that
    even if the DB is compromised, raw tokens are not exposed.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def get_user_by_id(user_id: str, db: AsyncSession) -> User | None:
    """
    Fetch a user from the database by their UUID.

    Args:
        user_id: The user UUID string (from JWT 'sub' claim).
        db: An active async database session.

    Returns:
        The User object if found, otherwise None.
    """
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return None

    result = await db.execute(select(User).where(User.id == uid))
    return result.scalar_one_or_none()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency that extracts the current authenticated user
    from the Bearer access token.

    Steps:
        1. Extract token from Authorization header
        2. Decode and validate the JWT
        3. Extract user ID from 'sub' claim
        4. Fetch the user from the database
        5. Return the user or raise 401

    Returns:
        The authenticated User object.

    Raises:
        HTTPException 401: If token is invalid, expired, or user not found.
    """
    token = credentials.credentials

    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
        )

    # ── Check if the access token has been blacklisted (e.g. logged out) ──
    jti = payload.get("jti")
    if jti:
        blacklisted = await db.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == jti)
        )
        if blacklisted.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token has been revoked.",
            )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token: missing subject.",
        )

    user = await get_user_by_id(user_id, db)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return user
