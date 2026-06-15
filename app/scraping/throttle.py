import asyncio
import logging
import random
import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def host_of(url: str) -> str:
    parsed = urlparse(url)
    return parsed.hostname.lower() if parsed.hostname else url.lower()


class _TokenBucket:
    """Simple token bucket for per-domain RPS limiting."""

    def __init__(self, rate: float) -> None:
        self._rate = rate  # tokens per second
        self._tokens: float = 1.0
        self._last_refill: float = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(1.0, self._tokens + elapsed * self._rate)
        self._last_refill = now

    async def acquire(self) -> None:
        while True:
            self._refill()
            # No await before this decrement, so it is atomic in one event loop.
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            wait = (1.0 - self._tokens) / self._rate
            await asyncio.sleep(wait)


class _CircuitBreaker:
    def __init__(self, threshold: int, cooldown_s: int) -> None:
        self._threshold = threshold
        self._cooldown_s = cooldown_s
        self._failures: int = 0
        self._opened_at: float | None = None

    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self._cooldown_s:
            self._failures = self._threshold - 1
            self._opened_at = None
            return False
        return True

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = time.monotonic()

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None


class _Throttle:
    def __init__(self) -> None:
        from app.config import settings

        self._global_sem = asyncio.Semaphore(settings.SCRAPER_MAX_CONCURRENCY)
        self._browser_sem = asyncio.Semaphore(settings.SCRAPER_BROWSER_CONCURRENCY)
        self._rps = settings.SCRAPER_PER_DOMAIN_RPS
        self._cb_threshold = settings.SCRAPER_CB_FAILURE_THRESHOLD
        self._cb_cooldown = settings.SCRAPER_CB_COOLDOWN_S
        self._buckets: dict[str, _TokenBucket] = {}
        self._breakers: dict[str, _CircuitBreaker] = {}

    def _bucket(self, host: str) -> _TokenBucket:
        if host not in self._buckets:
            self._buckets[host] = _TokenBucket(self._rps)
        return self._buckets[host]

    def _breaker(self, host: str) -> _CircuitBreaker:
        if host not in self._breakers:
            self._breakers[host] = _CircuitBreaker(self._cb_threshold, self._cb_cooldown)
        return self._breakers[host]

    @asynccontextmanager
    async def global_slot(self):
        async with self._global_sem:
            yield

    @asynccontextmanager
    async def browser_slot(self):
        async with self._browser_sem:
            yield

    async def acquire_domain(self, host: str) -> None:
        await self._bucket(host).acquire()

    def is_open(self, host: str) -> bool:
        return self._breaker(host).is_open()

    def record_failure(self, host: str) -> None:
        self._breaker(host).record_failure()

    def record_success(self, host: str) -> None:
        self._breaker(host).record_success()

    def backoff_delay(self, attempt: int) -> float:
        base = 1.0
        delay = base * (2**attempt)
        jitter = random.uniform(0, delay * 0.3)
        return delay + jitter

    @staticmethod
    def host_of(url: str) -> str:
        return host_of(url)


throttle: _Throttle = _Throttle()
