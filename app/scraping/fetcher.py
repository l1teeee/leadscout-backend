import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.scraping.browser_pool import browser_pool
from app.scraping.proxy_pool import proxy_pool
from app.scraping.throttle import throttle
from app.scraping.user_agents import browser_headers, random_user_agent

logger = logging.getLogger(__name__)

_MAX_BODY = 500_000


@dataclass
class FetchResult:
    html: str
    final_url: str
    status: int   # HTTP status from httpx; 0 when served by browser
    via: str      # "httpx" | "browser"


async def fetch(url: str) -> FetchResult | None:
    """Resilient GET. Returns FetchResult or None when the host is circuit-open,
    all retries failed, or the response wasn't usable HTML. Never raises."""
    from app.config import settings

    host = throttle.host_of(url)

    if throttle.is_open(host):
        logger.debug("Circuit open for %s, skipping fetch", host)
        return None

    max_attempts = settings.SCRAPER_MAX_RETRIES + 1

    for attempt in range(max_attempts):
        proxy = proxy_pool.get()

        await throttle.acquire_domain(host)
        if attempt > 0:
            await asyncio.sleep(throttle.backoff_delay(attempt - 1))
        async with throttle.global_slot():
            result = await _try_httpx(url, proxy, host, attempt)
        if result is not None:
            return result

    # httpx exhausted -- try browser fallback
    if await browser_pool.enabled():
        ua = random_user_agent()
        proxy = proxy_pool.get()
        async with throttle.browser_slot():
            br = await browser_pool.fetch_html(url, proxy=proxy, user_agent=ua)
        if br is not None:
            html, final_url = br
            throttle.record_success(host)
            return FetchResult(html=html, final_url=final_url, status=0, via="browser")
        throttle.record_failure(host)

    return None


async def _try_httpx(
    url: str,
    proxy: str | None,
    host: str,
    attempt: int,
) -> FetchResult | None:
    headers = browser_headers()

    try:
        async with httpx.AsyncClient(
            timeout=12,
            follow_redirects=True,
            proxy=proxy or None,
        ) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code in (403, 429):
            logger.debug("Blocked (%d) fetching %s (attempt %d)", resp.status_code, url, attempt)
            _on_failure(proxy, host)
            return None

        if not resp.is_success:
            logger.debug("Non-2xx (%d) fetching %s (attempt %d)", resp.status_code, url, attempt)
            _on_failure(proxy, host)
            return None

        ct = resp.headers.get("content-type", "")
        if "html" not in ct:
            logger.debug("Non-HTML content-type '%s' for %s", ct, url)
            _on_failure(proxy, host)
            return None

        encoding = resp.encoding or "utf-8"
        raw = resp.content[:_MAX_BODY]
        html = raw.decode(encoding, errors="ignore")

        if proxy:
            proxy_pool.mark_ok(proxy)
        throttle.record_success(host)
        return FetchResult(
            html=html,
            final_url=str(resp.url),
            status=resp.status_code,
            via="httpx",
        )

    except httpx.TransportError as exc:
        logger.debug("Transport error fetching %s (attempt %d): %s", url, attempt, exc)
        _on_failure(proxy, host)
        return None
    except Exception as exc:
        logger.warning("Unexpected error fetching %s: %s", url, exc)
        _on_failure(proxy, host)
        return None


def _on_failure(proxy: str | None, host: str) -> None:
    if proxy:
        proxy_pool.mark_bad(proxy)
    throttle.record_failure(host)
