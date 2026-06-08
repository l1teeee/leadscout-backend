import asyncio
import time
import pytest
from app.cache import _InMemoryCache, TTL_REPORTS, TTL_PLACES, TTL_PAGESPEED, TTL_AUTH_TOKEN


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestInMemoryCache:
    def test_set_and_get(self):
        cache = _InMemoryCache()
        run(cache.set("k", "v", ttl=60))
        assert run(cache.get("k")) == "v"

    def test_ttl_expiry(self, monkeypatch):
        cache = _InMemoryCache()
        run(cache.set("k", "v", ttl=10))
        original = time.monotonic
        monkeypatch.setattr(time, "monotonic", lambda: original() + 11)
        assert run(cache.get("k")) is None

    def test_delete(self):
        cache = _InMemoryCache()
        run(cache.set("k", "v", ttl=60))
        run(cache.delete("k"))
        assert run(cache.get("k")) is None

    def test_delete_nonexistent_key(self):
        cache = _InMemoryCache()
        run(cache.delete("nonexistent"))  # must not raise

    def test_invalidate_prefix(self):
        cache = _InMemoryCache()
        run(cache.set("prefix:a", 1, ttl=60))
        run(cache.set("prefix:b", 2, ttl=60))
        run(cache.set("other:c", 3, ttl=60))
        run(cache.invalidate_prefix("prefix:"))
        assert run(cache.get("prefix:a")) is None
        assert run(cache.get("prefix:b")) is None
        assert run(cache.get("other:c")) == 3

    def test_cleanup_triggers_at_capacity(self, monkeypatch):
        cache = _InMemoryCache()
        original = time.monotonic
        # Insert 1001 entries that are already expired
        for i in range(1001):
            cache._store[f"key:{i}"] = ("v", original() - 50)
        # set() should trigger _cleanup_expired and remove them
        run(cache.set("trigger", "v", ttl=60))
        assert len(cache._store) < 1001

    def test_ttl_constants_order(self):
        assert TTL_REPORTS < TTL_PLACES < TTL_PAGESPEED
        assert TTL_AUTH_TOKEN > 0
