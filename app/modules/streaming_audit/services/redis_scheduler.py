from __future__ import annotations

import json
from typing import Iterable

from redis.asyncio import Redis

from app.core.config import settings
from app.modules.streaming_audit.config import STREAMING_AUDIT_MAX_CONCURRENCY
from app.modules.streaming_audit.services.streaming_audit_service import normalize_url


class RedisQueueScheduler:
    """Redis-backed queue and dedupe coordination for the streaming audit."""

    _RESERVE_SLOT_SCRIPT = """
local active = tonumber(redis.call('GET', KEYS[1]) or '0')
local limit = tonumber(ARGV[1])
if active >= limit then
    return 0
end
return redis.call('INCR', KEYS[1])
"""
    _RELEASE_SLOT_SCRIPT = """
local active = tonumber(redis.call('GET', KEYS[1]) or '0')
if active > 0 then
    return redis.call('DECR', KEYS[1])
end
return 0
"""

    def __init__(self, redis_client: Redis | None = None):
        self.redis = redis_client or Redis.from_url(settings.REDIS_URL, decode_responses=True)

    def ns(self, audit_id: str) -> str:
        return f"streaming_audit:{audit_id}"

    async def is_seen(self, audit_id: str, url: str) -> bool:
        key = f"{self.ns(audit_id)}:seen"
        normalized = normalize_url(url)
        return bool(await self.redis.sismember(key, normalized))

    async def mark_seen(self, audit_id: str, url: str) -> bool:
        key = f"{self.ns(audit_id)}:seen"
        normalized = normalize_url(url)
        return bool(await self.redis.sadd(key, normalized))

    async def enqueue(self, audit_id: str, url: str, depth: int = 0, max_pages: int | None = None) -> bool:
        normalized = normalize_url(url)
        if not normalized:
            return False
        if await self.is_seen(audit_id, normalized):
            return False
        if max_pages is not None:
            remaining = int(await self.redis.get(f"{self.ns(audit_id)}:remaining") or max_pages)
            if remaining <= 0:
                return False
        if await self.mark_seen(audit_id, normalized):
            payload = json.dumps({"url": normalized, "depth": depth})
            await self.redis.rpush(f"{self.ns(audit_id)}:queued", payload)
            if max_pages is not None:
                await self.redis.decrby(f"{self.ns(audit_id)}:remaining", 1)
            return True
        return False

    async def enqueue_many(self, audit_id: str, urls: Iterable[str], depth: int = 0, max_pages: int | None = None) -> list[str]:
        queued: list[str] = []
        for value in urls:
            if max_pages is not None and int(await self.redis.get(f"{self.ns(audit_id)}:remaining") or max_pages) <= 0:
                break
            normalized = normalize_url(value)
            if not normalized:
                continue
            if await self.is_seen(audit_id, normalized):
                continue
            if await self.mark_seen(audit_id, normalized):
                payload = json.dumps({"url": normalized, "depth": depth})
                await self.redis.rpush(f"{self.ns(audit_id)}:queued", payload)
                queued.append(normalized)
                if max_pages is not None:
                    await self.redis.decrby(f"{self.ns(audit_id)}:remaining", 1)
        return queued

    async def reserve_slot(self, audit_id: str, limit: int | None = None) -> bool:
        limit = limit or STREAMING_AUDIT_MAX_CONCURRENCY
        active_key = f"{self.ns(audit_id)}:active"
        return bool(await self.redis.eval(self._RESERVE_SLOT_SCRIPT, 1, active_key, limit))

    async def release_slot(self, audit_id: str) -> None:
        active_key = f"{self.ns(audit_id)}:active"
        await self.redis.eval(self._RELEASE_SLOT_SCRIPT, 1, active_key)

    async def next_url(self, audit_id: str) -> tuple[str, int] | None:
        payload = await self.redis.lpop(f"{self.ns(audit_id)}:queued")
        if not payload:
            return None
        item = json.loads(payload)
        return item.get("url"), int(item.get("depth", 0))

    async def initialize_run(self, audit_id: str, seed_url: str, max_pages: int) -> None:
        ns = self.ns(audit_id)
        seen = normalize_url(seed_url)
        await self.redis.delete(f"{ns}:seen", f"{ns}:queued", f"{ns}:active", f"{ns}:remaining")
        await self.redis.sadd(f"{ns}:seen", seen)
        await self.redis.set(f"{ns}:remaining", max(0, max_pages - 1))
        await self.redis.rpush(f"{ns}:queued", json.dumps({"url": seen, "depth": 0}))

    async def has_pending_work(self, audit_id: str) -> bool:
        return bool(await self.redis.llen(f"{self.ns(audit_id)}:queued"))

    async def is_idle(self, audit_id: str) -> bool:
        active = int(await self.redis.get(f"{self.ns(audit_id)}:active") or 0)
        queued = int(await self.redis.llen(f"{self.ns(audit_id)}:queued") or 0)
        return active == 0 and queued == 0

    async def close(self) -> None:
        await self.redis.aclose()
