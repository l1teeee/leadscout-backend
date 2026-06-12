import time

from app.scraping.proxy_pool import _ProxyPool


def _pool(proxies: list[str], cooldown_s: int = 300) -> _ProxyPool:
    pool = _ProxyPool()
    pool._proxies = list(proxies)
    pool._index = 0
    pool._cooldown = {}
    pool._cooldown_s = cooldown_s
    return pool


class TestProxyPool:
    def test_empty_pool_returns_none(self):
        pool = _pool([])
        assert pool.get() is None

    def test_round_robin(self):
        pool = _pool(["p1", "p2", "p3"])
        assert [pool.get() for _ in range(4)] == ["p1", "p2", "p3", "p1"]

    def test_mark_bad_skips_until_cooldown(self):
        pool = _pool(["p1", "p2"], cooldown_s=300)
        pool.mark_bad("p1")
        # p1 is in cooldown, get() should only return p2
        assert {pool.get() for _ in range(4)} == {"p2"}

    def test_all_bad_returns_none(self):
        pool = _pool(["p1", "p2"])
        pool.mark_bad("p1")
        pool.mark_bad("p2")
        assert pool.get() is None

    def test_cooldown_expires(self, monkeypatch):
        pool = _pool(["p1"], cooldown_s=10)
        pool.mark_bad("p1")
        assert pool.get() is None
        original = time.monotonic
        monkeypatch.setattr(time, "monotonic", lambda: original() + 11)
        assert pool.get() == "p1"

    def test_mark_ok_clears_cooldown(self):
        pool = _pool(["p1", "p2"])
        pool.mark_bad("p1")
        pool.mark_ok("p1")
        assert {pool.get() for _ in range(4)} == {"p1", "p2"}

    def test_mark_bad_ignores_unknown_proxy(self):
        pool = _pool(["p1"])
        pool.mark_bad("not-in-pool")  # must not raise or add cooldown
        assert pool.get() == "p1"
