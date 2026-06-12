import asyncio
import time

from app.scraping.throttle import _CircuitBreaker, _Throttle, _TokenBucket, host_of


def run(coro):
    return asyncio.run(coro)


class TestHostOf:
    def test_extracts_hostname(self):
        assert host_of("https://www.Example.com/path") == "www.example.com"

    def test_no_hostname_falls_back(self):
        assert host_of("not-a-url") == "not-a-url"


class TestTokenBucket:
    def test_first_acquire_is_immediate(self):
        bucket = _TokenBucket(rate=0.5)
        run(bucket.acquire())  # starts with 1 token, returns at once

    def test_refill_grants_after_elapsed_time(self, monkeypatch):
        bucket = _TokenBucket(rate=1.0)  # 1 token/sec
        run(bucket.acquire())  # consume the initial token -> tokens ~0
        assert bucket._tokens < 1.0
        original = time.monotonic
        monkeypatch.setattr(time, "monotonic", lambda: original() + 2)
        bucket._refill()
        assert bucket._tokens >= 1.0  # 2s * 1 token/s, capped at 1.0


class TestCircuitBreaker:
    def test_opens_after_threshold(self):
        cb = _CircuitBreaker(threshold=3, cooldown_s=300)
        assert not cb.is_open()
        for _ in range(3):
            cb.record_failure()
        assert cb.is_open()

    def test_success_resets(self):
        cb = _CircuitBreaker(threshold=2, cooldown_s=300)
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        assert not cb.is_open()  # counter was reset, only 1 failure since

    def test_half_open_after_cooldown(self, monkeypatch):
        cb = _CircuitBreaker(threshold=2, cooldown_s=10)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open()
        original = time.monotonic
        monkeypatch.setattr(time, "monotonic", lambda: original() + 11)
        # cooldown elapsed -> half-open probe allowed
        assert not cb.is_open()
        # one tolerated failure before it re-trips (failures decayed to threshold-1)
        cb.record_failure()
        assert cb.is_open()


class TestThrottleService:
    def test_is_open_and_record_via_service(self):
        t = _Throttle()
        t._cb_threshold = 2
        host = "example.com"
        assert not t.is_open(host)
        t.record_failure(host)
        t.record_failure(host)
        assert t.is_open(host)
        t.record_success(host)
        assert not t.is_open(host)

    def test_backoff_grows_with_attempt(self):
        t = _Throttle()
        d0 = t.backoff_delay(0)
        d2 = t.backoff_delay(2)
        assert d0 >= 1.0
        assert d2 > d0  # exponential

    def test_global_slot_limits_concurrency(self):
        async def scenario():
            t = _Throttle()
            t._global_sem = asyncio.Semaphore(2)
            active = 0
            peak = 0

            async def worker():
                nonlocal active, peak
                async with t.global_slot():
                    active += 1
                    peak = max(peak, active)
                    await asyncio.sleep(0.01)
                    active -= 1

            await asyncio.gather(*(worker() for _ in range(6)))
            return peak

        peak = run(scenario())
        assert peak <= 2
