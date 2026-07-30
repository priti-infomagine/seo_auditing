"""
JWT token creation and verification utilities.

Generates access tokens (short-lived) and refresh tokens (long-lived)
using python-jose with HS256 algorithm.
"""
from datetime import datetime, timedelta, timezone

from jose import  jwt

from app.core.config import settings


def create_access_token(subject: str) -> str:
    """
    Create a short-lived JWT access token.

    Args:
        subject: The user identifier (UUID string) to embed in the token.

    Returns:
        Encoded JWT access token string.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    """
    Create a long-lived JWT refresh token.

    Args:
        subject: The user identifier (UUID string) to embed in the token.

    Returns:
        Encoded JWT refresh token string.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.

    Args:
        token: The JWT token string.

    Returns:
        Decoded payload dictionary.

    Raises:
        JWTError: If the token is invalid or expired.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])