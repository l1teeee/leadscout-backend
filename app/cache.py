"""
Dual-backend cache: in-memory TTL (default) or Redis (when REDIS_URL is set).

TTL guidelines:
  reports summary  → 2 min   (dashboard calls frequently, aggregation is expensive)
  Google Places    → 30 min  (external API quota + results are stable)
  PageSpeed        → 24 h    (website performance rarely changes within a day)
  auth token       → 5 min   (reduce Supabase auth API calls per request)
"""

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── TTL constants (seconds) ───────────────────────────────────────────────────
TTL_REPORTS = 120
TTL_PLACES = 1_800
TTL_PAGESPEED = 86_400
TTL_AUTH_TOKEN = 300


# ── Backends ──────────────────────────────────────────────────────────────────

class _InMemoryCache:
    """Single-process TTL cache. Safe for asyncio (single event-loop thread)."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}

    async def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: Any, ttl: int) -> None:
        self._cleanup_expired()
        self._store[key] = (value, time.monotonic() + ttl)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def invalidate_prefix(self, prefix: str) -> None:
        stale = [k for k in self._store if k.startswith(prefix)]
        for k in stale:
            del self._store[k]

    async def close(self) -> None:
        pass

    def _cleanup_expired(self) -> None:
        if len(self._store) < 1000:
            return
        now = time.monotonic()
        expired = [k for k, (_, expiry) in self._store.items() if now > expiry]
        for k in expired:
            del self._store[k]

    def __repr__(self) -> str:
        return "InMemoryCache"


class _RedisCache:
    """Redis-backed cache via redis.asyncio."""

    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis
        self._client = aioredis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Optional[Any]:
        raw = await self._client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        await self._client.setex(key, ttl, json.dumps(value, default=str))

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def invalidate_prefix(self, prefix: str) -> None:
        cursor = 0
        keys = []
        while True:
            cursor, batch = await self._client.scan(
                cursor=cursor,
                match=f"{prefix}*",
                count=100,
            )
            keys.extend(batch)
            if cursor == 0:
                break
        if keys:
            await self._client.delete(*keys)

    async def close(self) -> None:
        await self._client.aclose()

    def __repr__(self) -> str:
        return "RedisCache"


# ── Factory & singleton ───────────────────────────────────────────────────────

def _build() -> _InMemoryCache | _RedisCache:
    from app.config import settings
    if settings.REDIS_URL:
        try:
            c = _RedisCache(settings.REDIS_URL)
            logger.info("Cache backend: Redis (%s)", settings.REDIS_URL.split("@")[-1])
            return c
        except Exception as exc:
            logger.warning("Redis unavailable (%s) — falling back to in-memory cache", exc)
    logger.info("Cache backend: in-memory TTL")
    return _InMemoryCache()


cache: _InMemoryCache | _RedisCache = _build()
