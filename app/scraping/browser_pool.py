import logging
from typing import Any

logger = logging.getLogger(__name__)


class _BrowserPool:
    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._failed: bool = False  # cached launch failure

    async def enabled(self) -> bool:
        from app.config import settings

        if not settings.PLAYWRIGHT_ENABLED:
            return False
        if self._failed:
            return False
        if self._browser is not None:
            return True
        return await self._launch()

    async def _launch(self) -> bool:
        try:
            from playwright.async_api import async_playwright  # noqa: PLC0415

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            logger.info("Playwright browser launched")
            return True
        except Exception as exc:
            logger.warning("Playwright launch failed (%s) — browser fallback disabled", exc)
            self._failed = True
            self._playwright = None
            self._browser = None
            return False

    async def fetch_html(
        self,
        url: str,
        *,
        proxy: str | None,
        user_agent: str,
    ) -> tuple[str, str] | None:
        if self._browser is None:
            return None
        ctx = None
        try:
            ctx_opts: dict = {
                "user_agent": user_agent,
                "locale": "es-ES",
                "viewport": {"width": 1366, "height": 768},
            }
            if proxy:
                parsed = _parse_proxy(proxy)
                ctx_opts["proxy"] = parsed

            ctx = await self._browser.new_context(**ctx_opts)
            await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = await ctx.new_page()
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            html = await page.content()
            final_url = page.url
            if resp is not None:
                logger.debug("Browser fetched %s -> %s", url, resp.status)
            return html, final_url
        except Exception as exc:
            logger.warning("Browser fetch failed for %s: %s", url, exc)
            return None
        finally:
            if ctx is not None:
                try:
                    await ctx.close()
                except Exception:
                    pass

    async def close(self) -> None:
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None


def _parse_proxy(proxy_url: str) -> dict:
    """Convert 'http://user:pass@host:port' -> playwright proxy dict."""
    from urllib.parse import urlparse

    p = urlparse(proxy_url)
    result: dict = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
    if p.username:
        result["username"] = p.username
    if p.password:
        result["password"] = p.password
    return result


browser_pool: _BrowserPool = _BrowserPool()
