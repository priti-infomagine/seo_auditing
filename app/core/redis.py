"""Redis dependency for FastAPI routes."""
from __future__ import annotations

from typing import Optional

from redis.asyncio import Redis

from app.core.config import settings


_redis_client: Optional[Redis] = None


def get_redis() -> Optional[Redis]:
    """Provide a Redis client for dependency injection.

    Returns ``None`` if Redis is unreachable or not configured.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = Redis.from_url(
            settings.REDIS_URL, decode_responses=True, socket_timeout=2
        )
        return _redis_client
    except Exception:
        return None
