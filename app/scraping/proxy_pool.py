import logging
import time

logger = logging.getLogger(__name__)


class _ProxyPool:
    def __init__(self) -> None:
        from app.config import settings

        self._proxies: list[str] = list(settings.proxies_list)
        self._index: int = 0
        # proxy -> (fail_time,) when in cooldown
        self._cooldown: dict[str, float] = {}
        self._cooldown_s: int = settings.SCRAPER_CB_COOLDOWN_S

        if self._proxies:
            logger.info("Proxy pool: %d proxies loaded", len(self._proxies))
        else:
            logger.info("Proxy pool: empty, direct connections only")

    def get(self) -> str | None:
        if not self._proxies:
            return None
        now = time.monotonic()
        # Try each proxy once starting from current index
        for _ in range(len(self._proxies)):
            proxy = self._proxies[self._index % len(self._proxies)]
            self._index = (self._index + 1) % len(self._proxies)
            bad_until = self._cooldown.get(proxy)
            if bad_until is None or now >= bad_until:
                if bad_until is not None:
                    # cooldown expired, clear it
                    del self._cooldown[proxy]
                return proxy
        # All proxies in cooldown
        return None

    def mark_bad(self, proxy: str) -> None:
        if proxy and proxy in self._proxies:
            self._cooldown[proxy] = time.monotonic() + self._cooldown_s
            logger.warning("Proxy marked bad (cooldown %ds): %s", self._cooldown_s, proxy)

    def mark_ok(self, proxy: str) -> None:
        if proxy:
            self._cooldown.pop(proxy, None)


proxy_pool: _ProxyPool = _ProxyPool()
