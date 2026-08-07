"""
Auth utilities.

Password hashing, token creation/decoding, and related helpers.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import settings
from app.shared.utils.url_utils import get_domain, is_internal_link, normalize_url


def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its hashed version."""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.verify(plain_password, hashed_password)


def hash_token(token: str) -> str:
    """Hash a JWT token using SHA-256 for secure storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(subject: str) -> str:
    """Create a short-lived JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    """Create a long-lived JWT refresh token."""
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
    """Decode and validate a JWT token."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

def generate_otp_code(length: int = 6) -> str:
    """Generate a random numeric OTP code of specified length."""
    import random
    
    otp_code = str(random.randint(100000, 999999))
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.OTP_EXPIRE_MINUTES
        )
    return otp_code, expires_at

__all__ = [
    "hash_password",
    "verify_password",
    "hash_token",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "normalize_url",
    "get_domain",
    "is_internal_link",
    "generate_otp_code",
]
