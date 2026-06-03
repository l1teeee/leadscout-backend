import logging

import httpx

from app.cache import TTL_PAGESPEED, cache
from app.config import settings

logger = logging.getLogger(__name__)

_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


async def get_pagespeed_score(url: str) -> int | None:
    if not settings.PAGESPEED_API_KEY or not url:
        return None

    key = f"pagespeed:{url}"
    cached = await cache.get(key)
    if cached is not None:
        logger.debug("Cache hit: pagespeed %s", url)
        return cached

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(_API_URL, params={
                "url": url,
                "strategy": "mobile",
                "key": settings.PAGESPEED_API_KEY,
            })
            resp.raise_for_status()
            raw = (
                resp.json()
                .get("lighthouseResult", {})
                .get("categories", {})
                .get("performance", {})
                .get("score")
            )
            score = int(raw * 100) if raw is not None else None
            if score is not None:
                await cache.set(key, score, ttl=TTL_PAGESPEED)
            return score
    except Exception as exc:
        logger.warning("PageSpeed error for %s: %s", url, exc)
        return None
